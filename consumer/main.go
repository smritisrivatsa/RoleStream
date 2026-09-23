package main

import (
	"context"
	"fmt"
	"log"

	"github.com/segmentio/kafka-go"
)

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

		fmt.Printf("Received message: %s\n", string(msg.Value))
	}
}