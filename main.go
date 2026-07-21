package main

import (
	"net/http"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

type OnyxClient struct {
	BaseURL    string
	PAT        string
	HTTPClient *http.Client
}

func main() {
	server := mcp.NewServer(&mcp.Implementation{
		Name:    "Onyx",
		Version: "0.1.0",
	}, nil)

}
