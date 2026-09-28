package chunker

import (
	"strings"
	"testing"
)

func TestSectionsAndPrefix(t *testing.T) {
	desc := "About the role\n" + strings.Repeat("build things ", 60) +
		"\nRequirements\n" + strings.Repeat("go python ", 60)
	chunks := ChunkPosting(Meta{"Stripe", "SWE", "Seattle"}, desc)
	if len(chunks) != 2 {
		t.Fatalf("want 2 chunks, got %d", len(chunks))
	}
	for _, c := range chunks {
		if !strings.HasPrefix(c.Text, "Stripe | SWE | Seattle\n") {
			t.Errorf("missing prefix: %q", c.Text[:30])
		}
	}
}

func TestLongSectionWindows(t *testing.T) {
	desc := "Responsibilities\n" + strings.Repeat("word ", 500)
	if n := len(ChunkPosting(Meta{"A", "B", "C"}, desc)); n < 3 {
		t.Fatalf("expected windowing, got %d chunks", n)
	}
}

func TestNoHeadings(t *testing.T) {
	if n := len(ChunkPosting(Meta{"A", "B", "C"}, strings.Repeat("word ", 100))); n != 1 {
		t.Fatalf("got %d", n)
	}
}