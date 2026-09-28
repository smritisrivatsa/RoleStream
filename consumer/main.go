package main

import (
	"bytes"
	"context"
	"crypto/sha1"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/signal"
	"time"

	"github.com/segmentio/kafka-go"

	"rolestream/consumer/chunker"
)

const (
	topic      = "rolestream.public.postings"
	collection = "postings"
	embedURL   = "http://localhost:8001/embed"
	qdrantURL  = "http://localhost:6333"
)

var httpc = &http.Client{Timeout: 60 * time.Second}

type posting struct {
	ID          string          `json:"id"`
	Source      string          `json:"source"`
	Company     string          `json:"company"`
	Title       string          `json:"title"`
	Location    *string         `json:"location"`
	Description string          `json:"description"`
	SalaryMin   json.RawMessage `json:"salary_min"`
	SalaryMax   json.RawMessage `json:"salary_max"`
	Currency    *string         `json:"currency"`
	Status      string          `json:"status"`
	URL         *string         `json:"url"`
	UpdatedAt   string          `json:"updated_at"`
}

type Event struct {
	Before *posting `json:"before"`
	After  *posting `json:"after"`
	Op     string   `json:"op"`
}

// message handles both formats: unwrapped, or wrapped in {"schema","payload"}.
type message struct {
	Event
	Payload *Event `json:"payload"`
}

func str(p *string) string {
	if p == nil {
		return ""
	}
	return *p
}

// num returns nil for null, missing, or non-numeric (old struct-encoded) salaries.
func num(raw json.RawMessage) *float64 {
	var f *float64
	if err := json.Unmarshal(raw, &f); err != nil {
		return nil
	}
	return f
}

// pointID is a deterministic UUID so reprocessing an event overwrites, never duplicates.
func pointID(postingID string, idx int) string {
	h := sha1.Sum([]byte(fmt.Sprintf("%s:%d", postingID, idx)))
	h[6] = (h[6] & 0x0f) | 0x50
	h[8] = (h[8] & 0x3f) | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", h[0:4], h[4:6], h[6:8], h[8:10], h[10:16])
}

func doJSON(method, url string, body, out any) error {
	b, _ := json.Marshal(body)
	req, err := http.NewRequest(method, url, bytes.NewReader(b))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := httpc.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 300 {
		return fmt.Errorf("%s %s: %d %s", method, url, resp.StatusCode, data)
	}
	if out != nil {
		return json.Unmarshal(data, out)
	}
	return nil
}

func embed(texts []string) ([][]float32, error) {
	var out struct {
		Embeddings [][]float32 `json:"embeddings"`
	}
	if err := doJSON(http.MethodPost, embedURL, map[string]any{"texts": texts}, &out); err != nil {
		return nil, err
	}
	if len(out.Embeddings) != len(texts) {
		return nil, fmt.Errorf("got %d embeddings for %d texts", len(out.Embeddings), len(texts))
	}
	return out.Embeddings, nil
}

// deleteChunks removes a posting's points. If keep > 0, only chunks with index >= keep
// are removed (stale tail after a posting shrinks).
func deleteChunks(id string, keep int) error {
	must := []any{map[string]any{"key": "posting_id", "match": map[string]any{"value": id}}}
	if keep > 0 {
		must = append(must, map[string]any{"key": "chunk_index", "range": map[string]any{"gte": keep}})
	}
	return doJSON(http.MethodPost, qdrantURL+"/collections/"+collection+"/points/delete?wait=true",
		map[string]any{"filter": map[string]any{"must": must}}, nil)
}

func upsert(p *posting) error {
	chunks := chunker.ChunkPosting(chunker.Meta{Company: p.Company, Title: p.Title, Location: str(p.Location)}, p.Description)
	if len(chunks) == 0 {
		return deleteChunks(p.ID, 0)
	}
	texts := make([]string, len(chunks))
	for i, c := range chunks {
		texts[i] = c.Text
	}
	vecs, err := embed(texts)
	if err != nil {
		return err
	}
	points := make([]map[string]any, len(chunks))
	for i, c := range chunks {
		points[i] = map[string]any{
			"id":     pointID(p.ID, c.Index),
			"vector": vecs[i],
			"payload": map[string]any{
				"posting_id": p.ID, "chunk_index": c.Index, "section": c.Section, "text": c.Text,
				"company": p.Company, "title": p.Title, "location": str(p.Location),
				"source": p.Source, "url": str(p.URL), "currency": str(p.Currency),
				"salary_min": num(p.SalaryMin), "salary_max": num(p.SalaryMax),
				"updated_at": p.UpdatedAt,
			},
		}
	}
	if err := doJSON(http.MethodPut, qdrantURL+"/collections/"+collection+"/points?wait=true",
		map[string]any{"points": points}, nil); err != nil {
		return err
	}
	// New chunks are already searchable; now drop any stale tail.
	return deleteChunks(p.ID, len(chunks))
}

func textChanged(b, a *posting) bool {
	return b == nil || b.Status != "open" || b.Description != a.Description ||
		b.Title != a.Title || b.Company != a.Company || str(b.Location) != str(a.Location)
}

func handle(e *Event) error {
	switch e.Op {
	case "r", "c", "u":
		a := e.After
		if a == nil {
			return nil
		}
		if a.Status != "open" {
			return deleteChunks(a.ID, 0) // closed => remove from search
		}
		if e.Op == "u" && !textChanged(e.Before, a) {
			return nil // metadata-only change, nothing to re-embed
		}
		return upsert(a)
	case "d":
		if e.Before != nil {
			return deleteChunks(e.Before.ID, 0)
		}
	}
	return nil
}

func process(msg kafka.Message) {
	var m message
	if err := json.Unmarshal(msg.Value, &m); err != nil {
		log.Printf("offset %d: bad JSON, skipping: %v", msg.Offset, err)
		return
	}
	ev := m.Event
	if m.Payload != nil {
		ev = *m.Payload
	}
	var err error
	for attempt := 1; attempt <= 5; attempt++ {
		if err = handle(&ev); err == nil {
			log.Printf("offset %d op=%s ok", msg.Offset, ev.Op)
			return
		}
		log.Printf("offset %d attempt %d failed: %v", msg.Offset, attempt, err)
		time.Sleep(time.Duration(attempt) * 2 * time.Second)
	}
	log.Printf("offset %d: giving up after retries: %v", msg.Offset, err)
}

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()

	r := kafka.NewReader(kafka.ReaderConfig{
		Brokers:     []string{"localhost:9092"},
		GroupID:     "rolestream-consumer-v2",
		Topic:       topic,
		StartOffset: kafka.FirstOffset,
		MaxBytes:    10 << 20,
	})
	defer r.Close()

	log.Println("consuming", topic)
	for {
		msg, err := r.FetchMessage(ctx)
		if err != nil {
			if ctx.Err() != nil {
				return
			}
			log.Fatal(err)
		}
		if len(msg.Value) > 0 { // empty value = tombstone
			process(msg)
		}
		if err := r.CommitMessages(ctx, msg); err != nil {
			log.Println("commit:", err)
		}
	}
}
