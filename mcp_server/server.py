"""
LeadPro MCP Server
Exposes LeadPro automation tools to Claude via Model Context Protocol.

Run:  python server.py
Then add to Claude Desktop config or use with any MCP client.
"""
import json
import os
import sys
import time

# ── add tools folder to path ──────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from tools.scraper_tool  import (trigger_scraper, get_scraper_status,
                                  stop_scraper, import_leads)
from tools.email_tool    import (get_campaigns, create_campaign, send_campaign,
                                  get_send_status, stop_sending, get_leads,
                                  get_email_templates)
from tools.inbox_tool    import (sync_inbox, get_messages, classify_intent,
                                  reply_to_message, get_unread_interested,
                                  get_questions)
from tools.analytics_tool import (score_lead, get_top_leads, get_campaign_stats,
                                   get_lead_summary, get_today_activity)

# ── load config ───────────────────────────────────────────────────────────────
_cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
with open(_cfg_path) as f:
    CONFIG = json.load(f)

BOOKING_LINK = CONFIG.get("booking", {}).get("link", "http://localhost:5000/book")

# ── MCP server ────────────────────────────────────────────────────────────────
server = Server("leadpro-mcp")


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        # ── Scraper ────────────────────────────────────────────────────────────
        types.Tool(
            name="trigger_scraper",
            description=(
                "Start a Google Maps (GMB) scraper job to find local business leads. "
                "Returns a job_id — poll with get_scraper_status to get results."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "city":     {"type": "string", "description": "City to scrape (e.g. Delhi)"},
                    "country":  {"type": "string", "description": "Country (e.g. India)"},
                    "category": {"type": "string", "description": "Business type / niche (e.g. restaurant, gym, dentist)"},
                    "limit":    {"type": "integer", "description": "Max leads to collect (1-100, default 20)", "default": 20}
                },
                "required": ["city", "country", "category"]
            }
        ),
        types.Tool(
            name="get_scraper_status",
            description="Poll a running scraper job for logs and results.",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                    "offset": {"type": "integer", "default": 0}
                },
                "required": ["job_id"]
            }
        ),
        types.Tool(
            name="stop_scraper",
            description="Stop the currently running scraper job.",
            inputSchema={"type": "object", "properties": {}}
        ),
        types.Tool(
            name="import_scraped_leads",
            description="Import scraped lead objects into the LeadPro database.",
            inputSchema={
                "type": "object",
                "properties": {
                    "leads":          {"type": "array",  "description": "Array of lead objects from scraper"},
                    "service_needed": {"type": "string", "description": "Service tag for these leads"}
                },
                "required": ["leads"]
            }
        ),

        # ── Email ──────────────────────────────────────────────────────────────
        types.Tool(
            name="get_campaigns",
            description="List all saved email campaigns.",
            inputSchema={"type": "object", "properties": {}}
        ),
        types.Tool(
            name="create_campaign",
            description="Create a new email campaign with a subject and HTML body.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name":    {"type": "string"},
                    "service": {"type": "string", "description": "Comma-separated services this campaign targets"},
                    "subject": {"type": "string"},
                    "body":    {"type": "string", "description": "Full HTML email body"}
                },
                "required": ["name", "service", "subject", "body"]
            }
        ),
        types.Tool(
            name="send_campaign",
            description="Send an email campaign to a list of lead IDs.",
            inputSchema={
                "type": "object",
                "properties": {
                    "lead_ids":    {"type": "array",   "items": {"type": "integer"}},
                    "campaign_id": {"type": "integer"}
                },
                "required": ["lead_ids", "campaign_id"]
            }
        ),
        types.Tool(
            name="get_send_status",
            description="Get real-time email sending progress (sent/failed/total).",
            inputSchema={"type": "object", "properties": {}}
        ),
        types.Tool(
            name="stop_sending",
            description="Stop the current email sending run.",
            inputSchema={"type": "object", "properties": {}}
        ),
        types.Tool(
            name="get_leads",
            description="Fetch leads from the database.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50}
                }
            }
        ),
        types.Tool(
            name="get_email_templates",
            description="Return all built-in email templates for every service.",
            inputSchema={"type": "object", "properties": {}}
        ),

        # ── Inbox ──────────────────────────────────────────────────────────────
        types.Tool(
            name="sync_inbox",
            description="Sync the IMAP inbox and store new replies in the database.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 30}
                }
            }
        ),
        types.Tool(
            name="get_inbox_messages",
            description="Return all inbox messages with replied status.",
            inputSchema={"type": "object", "properties": {}}
        ),
        types.Tool(
            name="classify_reply_intent",
            description="Classify a reply text as: interested | not_interested | question | unknown.",
            inputSchema={
                "type": "object",
                "properties": {
                    "body_text": {"type": "string"}
                },
                "required": ["body_text"]
            }
        ),
        types.Tool(
            name="reply_to_message",
            description="Send an email reply to a specific inbox message.",
            inputSchema={
                "type": "object",
                "properties": {
                    "msg_id":    {"type": "integer"},
                    "to_email":  {"type": "string"},
                    "subject":   {"type": "string"},
                    "body":      {"type": "string", "description": "HTML body of reply"}
                },
                "required": ["msg_id", "to_email", "subject", "body"]
            }
        ),
        types.Tool(
            name="get_interested_leads_from_inbox",
            description="Return unreplied inbox messages where the lead expressed interest.",
            inputSchema={"type": "object", "properties": {}}
        ),
        types.Tool(
            name="get_inbox_questions",
            description="Return unreplied inbox messages that contain a question.",
            inputSchema={"type": "object", "properties": {}}
        ),

        # ── Meeting / Calendly ─────────────────────────────────────────────────
        types.Tool(
            name="schedule_meeting",
            description=(
                "Send a meeting/demo scheduling email to a lead with a booking link. "
                "Use this when a lead is interested and wants to talk."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "msg_id":        {"type": "integer", "description": "Inbox message ID to reply to"},
                    "to_email":      {"type": "string"},
                    "business_name": {"type": "string"},
                    "sender_name":   {"type": "string", "default": "Solvinex Team"},
                    "booking_link":  {"type": "string", "description": "Override default booking link (optional)"}
                },
                "required": ["msg_id", "to_email", "business_name"]
            }
        ),

        # ── Analytics ─────────────────────────────────────────────────────────
        types.Tool(
            name="score_lead",
            description="Score a single lead object 0-100 based on data completeness and SEO opportunity.",
            inputSchema={
                "type": "object",
                "properties": {
                    "lead": {"type": "object", "description": "Lead dict from get_leads"}
                },
                "required": ["lead"]
            }
        ),
        types.Tool(
            name="get_top_leads",
            description="Return top-scored new leads from the database.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 20}
                }
            }
        ),
        types.Tool(
            name="get_campaign_stats",
            description="Return sent/failed counts for all campaigns.",
            inputSchema={"type": "object", "properties": {}}
        ),
        types.Tool(
            name="get_lead_summary",
            description="Return lead counts broken down by status, source, and service.",
            inputSchema={"type": "object", "properties": {}}
        ),
        types.Tool(
            name="get_today_activity",
            description="Return today's email sent/failed count and new leads added.",
            inputSchema={"type": "object", "properties": {}}
        ),
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL CALL HANDLER
# ═══════════════════════════════════════════════════════════════════════════════

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:

    def out(data) -> list[types.TextContent]:
        text = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        return [types.TextContent(type="text", text=text)]

    # ── Scraper ────────────────────────────────────────────────────────────────
    if name == "trigger_scraper":
        result = trigger_scraper(
            arguments["city"],
            arguments["country"],
            arguments["category"],
            arguments.get("limit", 20)
        )
        return out(result)

    if name == "get_scraper_status":
        result = get_scraper_status(arguments["job_id"], arguments.get("offset", 0))
        return out(result)

    if name == "stop_scraper":
        return out(stop_scraper())

    if name == "import_scraped_leads":
        result = import_leads(
            arguments["leads"],
            arguments.get("service_needed", "Website Development")
        )
        return out(result)

    # ── Email ──────────────────────────────────────────────────────────────────
    if name == "get_campaigns":
        return out(get_campaigns())

    if name == "create_campaign":
        result = create_campaign(
            arguments["name"],
            arguments["service"],
            arguments["subject"],
            arguments["body"]
        )
        return out(result)

    if name == "send_campaign":
        result = send_campaign(arguments["lead_ids"], arguments["campaign_id"])
        return out(result)

    if name == "get_send_status":
        return out(get_send_status())

    if name == "stop_sending":
        return out(stop_sending())

    if name == "get_leads":
        return out(get_leads(arguments.get("limit", 50)))

    if name == "get_email_templates":
        return out(get_email_templates())

    # ── Inbox ──────────────────────────────────────────────────────────────────
    if name == "sync_inbox":
        return out(sync_inbox(arguments.get("limit", 30)))

    if name == "get_inbox_messages":
        return out(get_messages())

    if name == "classify_reply_intent":
        intent = classify_intent(arguments["body_text"])
        return out({"intent": intent})

    if name == "reply_to_message":
        result = reply_to_message(
            arguments["msg_id"],
            arguments["to_email"],
            arguments["subject"],
            arguments["body"]
        )
        return out(result)

    if name == "get_interested_leads_from_inbox":
        return out(get_unread_interested())

    if name == "get_inbox_questions":
        return out(get_questions())

    # ── Meeting / Booking ──────────────────────────────────────────────────────
    if name == "schedule_meeting":
        link = arguments.get("booking_link") or BOOKING_LINK
        biz  = arguments.get("business_name", "there")
        sender = arguments.get("sender_name", "Solvinex Team")
        body = f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#333">
<h2 style="color:#2563eb">Hi {biz},</h2>
<p>Thank you for your interest! I'd love to connect and discuss how we can help grow your business.</p>
<p>Please pick a time that works best for you:</p>
<p style="text-align:center;margin:30px 0">
  <a href="{link}" style="background:#2563eb;color:#fff;padding:14px 28px;border-radius:8px;text-decoration:none;font-weight:700;font-size:16px">
    📅 Book a Free 15-Minute Call
  </a>
</p>
<p>The call takes about 15 minutes and I'll walk you through exactly what we can do for {biz}.</p>
<p>Looking forward to speaking with you!</p>
<br><p>Best regards,<br><strong>{sender}</strong></p>
</div>"""
        result = reply_to_message(
            arguments["msg_id"],
            arguments["to_email"],
            f"Let's schedule a quick call — {biz}",
            body
        )
        return out({**result, "booking_link": link})

    # ── Analytics ─────────────────────────────────────────────────────────────
    if name == "score_lead":
        return out(score_lead(arguments["lead"]))

    if name == "get_top_leads":
        return out(get_top_leads(arguments.get("limit", 20)))

    if name == "get_campaign_stats":
        return out(get_campaign_stats())

    if name == "get_lead_summary":
        return out(get_lead_summary())

    if name == "get_today_activity":
        return out(get_today_activity())

    return out({"error": f"Unknown tool: {name}"})


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRYPOINT
# ═══════════════════════════════════════════════════════════════════════════════

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream,
                         server.create_initialization_options())

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
