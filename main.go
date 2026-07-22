package main

import (
	"context"
	"log"
	"os"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

func main() {
	baseURL := os.Getenv("ONYX_URL")
	pat := os.Getenv("ONYX_PAT")
	if baseURL == "" || pat == "" {
		log.Fatal("ONYX_URL and ONYX_PAT must be set")
	}

	client := NewOnyxClient(baseURL, pat)
	server := mcp.NewServer(&mcp.Implementation{
		Name:    "onyx",
		Version: "0.1.0",
	}, nil)
	registerProjectTools(server, client)
	registerVDITools(server, client)

	if err := server.Run(context.Background(), &mcp.StdioTransport{}); err != nil {
		log.Printf("Onyx MCP server stopped: %v", err)
	}
}
