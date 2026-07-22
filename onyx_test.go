package main

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestToolsCallExpectedOnyxRoutes(t *testing.T) {
	t.Helper()
	var calls []string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if got := r.Header.Get("Authorization"); got != "Bearer test-pat" {
			t.Errorf("Authorization = %q, want bearer PAT", got)
		}
		body, _ := io.ReadAll(r.Body)
		calls = append(calls, r.Method+" "+r.URL.RequestURI()+" "+string(body))
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"id": 1, "name": "Pump"}`))
	}))
	defer server.Close()

	client := NewOnyxClient(server.URL, "test-pat")
	ctx := context.Background()
	if _, _, err := client.ListAllProjects(ctx, nil, ListAllProjectsInput{}); err != nil {
		t.Fatal(err)
	}
	if _, _, err := client.GetSingleProject(ctx, nil, GetSingleProjectInput{ProjectID: 2}); err != nil {
		t.Fatal(err)
	}
	description := "scope"
	if _, _, err := client.CreateProject(ctx, nil, CreateProjectInput{"P-1", "Project", &description}); err != nil {
		t.Fatal(err)
	}
	_, staged, err := client.StageProjectUpdate(ctx, nil, StageProjectUpdateInput{ProjectID: 2, ProjectName: stringPointer("Renamed")})
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(staged.(string), "Do not show the stage key") {
		t.Fatalf("stage response = %q", staged)
	}
	client.stagedProjectsMu.Lock()
	var stageKey string
	for stageKey = range client.stagedProjects {
	}
	client.stagedProjectsMu.Unlock()
	if _, _, err := client.FinalizeProjectUpdate(ctx, nil, FinalizeProjectUpdateInput{StageKey: stageKey}); err != nil {
		t.Fatal(err)
	}
	if _, _, err := client.GetAllVendorDataForProject(ctx, nil, GetAllVendorDataForProjectInput{ProjectID: 2}); err != nil {
		t.Fatal(err)
	}
	if _, _, err := client.GetVendorDataItem(ctx, nil, GetVendorDataItemInput{VDIID: 3}); err != nil {
		t.Fatal(err)
	}
	if _, _, err := client.GetRevisionsForVDI(ctx, nil, GetRevisionsForVDIInput{VDIID: 3}); err != nil {
		t.Fatal(err)
	}
	if _, _, err := client.CreateVendorDataItem(ctx, nil, CreateVendorDataItemInput{ProjectID: 2, ItemNumber: 4, Name: "Pump", ApprovalType: "mandatory_approval", SubmitCode: "pti"}); err != nil {
		t.Fatal(err)
	}

	want := []string{
		"GET /api/projects ",
		"GET /api/projects/2 ",
		"POST /api/projects {\"project_number\":\"P-1\",\"name\":\"Project\",\"description\":\"scope\"}",
		"PATCH /api/projects/2 {\"id\":2,\"name\":\"Renamed\"}",
		"GET /api/vdi?project_id=2 ",
		"GET /api/vdi/3 ",
		"GET /api/vdi/3/revisions ",
	}
	if len(calls) != len(want)+1 {
		t.Fatalf("requests = %d, want %d: %#v", len(calls), len(want)+1, calls)
	}
	for i, expected := range want {
		if calls[i] != expected {
			t.Errorf("request %d = %q, want %q", i, calls[i], expected)
		}
	}

	var payload CreateVendorDataItemInput
	if err := json.Unmarshal([]byte(strings.TrimPrefix(calls[7], "POST /api/vdi ")), &payload); err != nil {
		t.Fatal(err)
	}
	if payload.ProjectID != 2 || payload.ItemNumber != 4 || payload.Name != "Pump" || payload.ApprovalType != "mandatory_approval" || payload.SubmitCode != "pti" {
		t.Errorf("unexpected VDI payload: %#v", payload)
	}
}

func TestOnyxErrorExplainsUnauthorized(t *testing.T) {
	err := onyxError(&apiError{StatusCode: http.StatusUnauthorized, Status: "401 Unauthorized"})
	if !strings.Contains(err.Error(), "missing, expired, or revoked") {
		t.Fatalf("error = %q", err)
	}
}

func stringPointer(value string) *string { return &value }
