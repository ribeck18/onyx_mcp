package main

import (
	"context"
	"fmt"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

type GetAllVendorDataForProjectInput struct {
	ProjectID int `json:"project_id" jsonschema:"the project's internal ID; use list_all_projects to find it"`
}

type GetVendorDataItemInput struct {
	VDIID int `json:"vdi_id" jsonschema:"the vendor data item's internal ID"`
}

type GetRevisionsForVDIInput struct {
	VDIID int `json:"vdi_id" jsonschema:"the vendor data item's internal ID"`
}

var approvalTypes = map[string]bool{
	"mandatory_approval": true,
	"information_only":   true,
}

var submitCodes = map[string]bool{
	"ac": true, "afi": true, "aro": true, "at": true, "bc": true, "bfa": true,
	"bfs": true, "pds": true, "ps": true, "pt": true, "ptc": true, "pti": true,
	"ptp": true, "ptw": true, "ros": true, "ts": true,
}

type CreateVendorDataItemInput struct {
	ProjectID            int     `json:"project_id" jsonschema:"the project's internal ID"`
	ItemNumber           int     `json:"item_number" jsonschema:"the buyer-assigned item number"`
	Name                 string  `json:"name" jsonschema:"the vendor data item name"`
	ApprovalType         string  `json:"approval_type" jsonschema:"mandatory_approval or information_only"`
	SubmitCode           string  `json:"submit_code" jsonschema:"one of ac, afi, aro, at, bc, bfa, bfs, pds, ps, pt, ptc, pti, ptp, ptw, ros, or ts"`
	SubmittalNumber      *string `json:"submittal_number,omitempty" jsonschema:"the optional submittal number"`
	Description          *string `json:"description,omitempty" jsonschema:"an optional description"`
	SpecDrawingReference *string `json:"spec_drawing_reference,omitempty" jsonschema:"an optional specification or drawing reference"`
	Notes                *string `json:"notes,omitempty" jsonschema:"optional notes"`
}

func registerVDITools(server *mcp.Server, client *OnyxClient) {
	mcp.AddTool(server, &mcp.Tool{
		Name:        "get_all_vendor_data_for_project",
		Description: "List every vendor data item for a project, including item number, submittal number, status, and update time.",
	}, client.GetAllVendorDataForProject)
	mcp.AddTool(server, &mcp.Tool{
		Name:        "get_vendor_data_item",
		Description: "Get the complete details of one vendor data item.",
	}, client.GetVendorDataItem)
	mcp.AddTool(server, &mcp.Tool{
		Name:        "get_revisions_for_vdi",
		Description: "Get all revisions for a vendor data item.",
	}, client.GetRevisionsForVDI)
	mcp.AddTool(server, &mcp.Tool{
		Name:        "create_new_vendor_data_item",
		Description: "Create a vendor data item for a project.",
	}, client.CreateVendorDataItem)
}

func (c *OnyxClient) GetAllVendorDataForProject(ctx context.Context, _ *mcp.CallToolRequest, input GetAllVendorDataForProjectInput) (*mcp.CallToolResult, any, error) {
	vdis, err := c.apiGet(ctx, fmt.Sprintf("vdi?project_id=%d", input.ProjectID))
	if err != nil {
		return nil, nil, onyxError(err)
	}
	return formattedResult(vdis)
}

func (c *OnyxClient) GetVendorDataItem(ctx context.Context, _ *mcp.CallToolRequest, input GetVendorDataItemInput) (*mcp.CallToolResult, any, error) {
	vdi, err := c.apiGet(ctx, fmt.Sprintf("vdi/%d", input.VDIID))
	if err != nil {
		return nil, nil, onyxError(err)
	}
	return formattedResult(vdi)
}

func (c *OnyxClient) GetRevisionsForVDI(ctx context.Context, _ *mcp.CallToolRequest, input GetRevisionsForVDIInput) (*mcp.CallToolResult, any, error) {
	revisions, err := c.apiGet(ctx, fmt.Sprintf("vdi/%d/revisions", input.VDIID))
	if err != nil {
		return nil, nil, onyxError(err)
	}
	return formattedResult(revisions)
}

func (c *OnyxClient) CreateVendorDataItem(ctx context.Context, _ *mcp.CallToolRequest, input CreateVendorDataItemInput) (*mcp.CallToolResult, any, error) {
	if !approvalTypes[input.ApprovalType] {
		return nil, nil, fmt.Errorf("approval_type must be mandatory_approval or information_only")
	}
	if !submitCodes[input.SubmitCode] {
		return nil, nil, fmt.Errorf("invalid submit_code %q", input.SubmitCode)
	}

	vdi, err := c.apiPost(ctx, "vdi", input)
	if err != nil {
		return nil, nil, onyxError(err)
	}
	return formattedResult(vdi)
}
