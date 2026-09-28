package chunker

import (
	"fmt"
	"regexp"
	"strings"
)

const (
	targetWords  = 160 // window size when a section is too long
	overlapWords = 30
	maxWords     = 200 // sections up to this size stay whole
	minWords     = 40  // smaller sections merge into the previous one
)

type Meta struct {
	Company, Title, Location string
}

type Chunk struct {
	Index   int
	Section string
	Text    string // includes the context prefix; this is what gets embedded
}

var headingRe = regexp.MustCompile(`(?i)(about|responsibilit|requirement|qualification|what you|who you|you have|you'll|you will|the role|benefit|perk|compensation|salary|pay range|why join|nice to have|preferred|minimum)`)

func isHeading(line string) bool {
	line = strings.TrimSpace(line)
	if line == "" || len(strings.Fields(line)) > 8 || strings.HasSuffix(line, ".") {
		return false
	}
	return headingRe.MatchString(line)
}

type section struct {
	name  string
	words []string
}

func ChunkPosting(m Meta, description string) []Chunk {
	prefix := fmt.Sprintf("%s | %s | %s\n", m.Company, m.Title, m.Location)

	// 1. split into sections on heading lines
	var secs []section
	cur := section{name: "intro"}
	for _, line := range strings.Split(description, "\n") {
		if isHeading(line) {
			if len(cur.words) > 0 {
				secs = append(secs, cur)
			}
			cur = section{name: strings.TrimSpace(strings.TrimSuffix(line, ":"))}
			continue
		}
		cur.words = append(cur.words, strings.Fields(line)...)
	}
	if len(cur.words) > 0 {
		secs = append(secs, cur)
	}

	// 2. merge tiny sections into the previous one
	var merged []section
	for _, s := range secs {
		if len(s.words) < minWords && len(merged) > 0 {
			last := &merged[len(merged)-1]
			last.words = append(last.words, append([]string{s.name + ":"}, s.words...)...)
			continue
		}
		merged = append(merged, s)
	}

	// 3. emit chunks; window long sections with overlap
	var out []Chunk
	emit := func(name string, w []string) {
		out = append(out, Chunk{
			Index:   len(out),
			Section: name,
			Text:    prefix + strings.Join(w, " "),
		})
	}
	for _, s := range merged {
		if len(s.words) <= maxWords {
			emit(s.name, s.words)
			continue
		}
		step := targetWords - overlapWords
		for start := 0; start < len(s.words); start += step {
			end := min(start+targetWords, len(s.words))
			emit(s.name, s.words[start:end])
			if end == len(s.words) {
				break
			}
		}
	}
	return out
}