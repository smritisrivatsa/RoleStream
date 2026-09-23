package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"

	"github.com/segmentio/kafka-go"
)

// Posting matches the fields in postings table.
// json tags map Go field names to the JSON keys Debezium sends.
type Posting struct {
	ID             string  `json:"id"`
	Source         string  `json:"source"`
	SourceID       string  `json:"source_id"`
	Company        string  `json:"company"`
	Title          string  `json:"title"`
	Department     *string `json:"department"`
	Location       *string `json:"location"`
	Description    string  `json:"description"`
	EmploymentType *string `json:"employment_type"`
	Status         string  `json:"status"`
	URL            *string `json:"url"`
}

// DebeziumPayload matches the "payload" section of every Debezium message.
type DebeziumPayload struct {
	Before *Posting `json:"before"`
	After  *Posting `json:"after"`
	Op     string   `json:"op"`
}

// DebeziumMessage is the top-level structure; we only care about "payload".
type DebeziumMessage struct {
	Payload DebeziumPayload `json:"payload"`
}

func main() {
	reader := kafka.NewReader(kafka.ReaderConfig{
		Brokers: []string{"localhost:9092"},
		Topic:   "rolestream.public.postings",
		GroupID: "rolestream-consumer-group",
	})
	defer reader.Close()

	fmt.Println("Consumer started, listening for messages...")

	ctx := context.Background()
	for {
		msg, err := reader.ReadMessage(ctx)
		if err != nil {
			log.Fatalf("error reading message: %v", err)
		}

		var event DebeziumMessage
		if err := json.Unmarshal(msg.Value, &event); err != nil {
			log.Printf("failed to parse message: %v", err)
			continue
		}

		handleEvent(event.Payload)
	}
}

func handleEvent(payload DebeziumPayload) {
	switch payload.Op {
	case "r", "c":
		// Initial snapshot read, or a genuine new insert
		fmt.Printf("[INSERT] %s at %s (id=%s)\n", payload.After.Title, payload.After.Company, payload.After.ID)

	case "u":
		// An update. Check specifically whether status changed to "closed".
		if payload.Before != nil && payload.Before.Status != "closed" && payload.After.Status == "closed" {
			fmt.Printf("[CLOSED] %s at %s (id=%s)\n", payload.After.Title, payload.After.Company, payload.After.ID)
		} else {
			fmt.Printf("[UPDATE] %s at %s (id=%s)\n", payload.After.Title, payload.After.Company, payload.After.ID)
		}

	default:
		fmt.Printf("[UNKNOWN OP: %s]\n", payload.Op)
	}
}