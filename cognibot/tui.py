"""
CogniBot TUI — A premium terminal interface based on the OpenCode aesthetic.
Features a responsive sidebar for tool calls and a clean, sharp-cornered chat stream.
"""

import asyncio
import json
from datetime import datetime
from typing import Any, List, Optional

from rich.console import RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Footer, Header, Input, Static, Select

from cognibot.agent import AgentDeps
from pydantic_ai import Agent


class MessageWidget(Static):
    """A single message turn in the chat."""

    def __init__(self, role: str, content: str, is_thinking: bool = False):
        super().__init__(classes=f"message message-{role}")
        self.role = role
        self.content = content
        self.is_thinking = is_thinking

    def render(self) -> RenderableType:
        if self.role == "user":
            return Text.from_markup(f"[bold green]You[/bold green]\n{self.content}")
        elif self.is_thinking:
            return Text.from_markup(f"[dim italic]Thinking: {self.content}[/dim italic]")
        else:
            # Render markdown for agent responses
            return Markdown(self.content)



class ToolCallWidget(Static):
    """A widget for the sidebar representing a tool call."""

    def __init__(self, tool_name: str, args: dict):
        super().__init__()
        self.tool_name = tool_name
        self.args = args
        self.status = "running"
        self.result = ""

    def update_result(self, result: str, success: bool):
        self.status = "success" if success else "error"
        self.result = result
        self.refresh()

    def render(self) -> RenderableType:
        status_color = "yellow" if self.status == "running" else ("green" if self.status == "success" else "red")
        status_icon = "⏳" if self.status == "running" else ("✅" if self.status == "success" else "❌")
        
        content = [
            f"[{status_color}]{status_icon} {self.tool_name}[/]",

            f"[dim]{json.dumps(self.args, indent=2)}[/dim]"
        ]
        if self.result:
            content.append(f"[dim]Result: {self.result[:100]}...[/dim]")
            
        return Panel(
            "\n".join(content),
            border_style=status_color,
            title="Tool Call",
            title_align="left",
        )


class CogniBotTUI(App):
    """Main TUI app for CogniBot."""

    CSS = """
    Screen {
    background: #050505;
}

#main-layout {
    layout: horizontal;
    height: 1fr;
    padding: 1 2;
}

#main-column {
    width: 7fr;
    height: 1fr;
    margin-right: 2;
    background: transparent;
    layout: vertical;
}

#sidebar {
    width: 3fr;
    height: 1fr;
    background: #161618;
    padding: 1 2;
    layout: vertical;
}

#think-select {
    margin: 1 0;
    height: auto;
}

#tool-calls-list {
    height: 1fr;
    margin-top: 1;
}

#chat-area {
    height: 1fr;
    background: #161618;
    padding: 1 2;
    overflow-y: auto;
}

#input-container {
    height: auto;
    min-height: 3;
    background: #161618;
    padding: 1 2;
    margin-top: 2; 
}

Input {
    border: none;
    background: #1e1e22;
    padding: 0 1;
}

Input:focus {
    border: none;
}

.sidebar-title {
    text-style: bold;
    margin-bottom: 1;
    color: $accent;
}

.thinking-line {
    color: $text-muted;
    text-style: italic;
    margin-bottom: 1;
}

.message {
    padding: 1 2;
    margin-bottom: 1;
    background: transparent;
}

.message-user {
    border-left: solid $success;
}

.message-bot {
    border-left: solid $accent;
}

VerticalScroll > .vertical-scrollbar {
    width: 1;
    background: transparent;
}

#welcome-banner {
    content-align: center middle;
    height: 1fr;
    text-style: bold;
    color: $accent;
    padding: 2;
}
"""

    def __init__(self, agent: Agent, deps: AgentDeps, history: List[Any] = None):
        super().__init__()
        self.agent = agent
        self.deps = deps
        self.history: List[Any] = []
        self.msg_count = 0
        # Inject TUI hooks into deps
        self.deps.tui_on_tool_start = self.on_tool_start
        self.deps.tui_on_tool_end = self.on_tool_end

    def compose(self) -> ComposeResult:
        with Horizontal(id="main-layout"):
            with Vertical(id="main-column"):
                with VerticalScroll(id="chat-area"):
                    yield Static("COGNIBOT", id="welcome-banner")
                with Vertical(id="input-container"):
                    yield Input(placeholder="Type your command here...", id="chat-input")
            with Vertical(id="sidebar"):
                yield Static("ACTIVE CONTEXT", classes="sidebar-title")
                yield Static(f"Model: [dim]{self.deps.config.llm_model}[/dim]")
                yield Select(
                    [("Low", "low"), ("Medium", "medium"), ("High", "high")],
                    value="medium",
                    id="think-select",
                    prompt="Thinking Mode"
                )
                yield Static("\nMODIFIED TOOLS", classes="sidebar-title")
                yield VerticalScroll(id="tool-calls-list")


    def on_mount(self) -> None:
        self.query_one("#chat-input").focus()

    @on(Input.Submitted)
    def handle_input(self, event: Input.Submitted) -> None:
        user_text = event.value.strip()
        if not user_text:
            return
        
        if user_text.lower() in ("exit", "quit", "q"):
            self.exit()
            return
            
        try:
            banner = self.query_one("#welcome-banner")
            banner.remove()
        except Exception:
            pass

        self.query_one("#chat-input").value = ""

        self.add_message("user", user_text)
        timestamped_input = f"[Current Local Time: {datetime.now().isoformat()}]\n{user_text}"
        self.run_agent(timestamped_input)

    def add_message(self, role: str, content: str, is_thinking: bool = False) -> MessageWidget:
        chat_area = self.query_one("#chat-area")
        widget = MessageWidget(role, content, is_thinking)
        chat_area.mount(widget)
        widget.scroll_visible()
        return widget

    @work(exclusive=True)
    async def run_agent(self, user_input: str) -> None:
        chat_area = self.query_one("#chat-area")
        self.msg_count += 1
        now = datetime.now().strftime("%H:%M")
        context_prefix = f"[[Msg #{self.msg_count}, {now}]] "
        full_input = context_prefix + user_input

        # UI placeholder while waiting
        if not (response_widget := getattr(self, "last_response_widget", None)):
            response_widget = self.add_message("bot", "⏳ Thinking...")
        
        try:
            think_mode = self.query_one("#think-select").value
            # 1. Switch from run_stream to run (Non-streaming)
            # This waits for the full response from Ollama/Proxy
            result = await self.agent.run(
                full_input,
                deps=self.deps,
                message_history=self.history if self.history else None,
                # Ensure thinking is requested
                model_settings={"thinking": think_mode}, 
            )

            # 2. Extract the final text content
            # PydanticAI automatically gathers all TextParts into result.data
            final_text = result.output

            # 3. Update the UI with the final answer
            response_widget.content = final_text
            response_widget.refresh()

            # 4. Save the history (Standard PydanticAI practice)
            self.history.extend(result.new_messages())

                
        except Exception as e:
            self.add_message("system", f"Error: {str(e)}")

    # ── Tool Call Hooks ──────────────────────────────────────────────

    def on_tool_start(self, name: str, args: dict) -> ToolCallWidget:
        tool_list = self.query_one("#tool-calls-list")
        widget = ToolCallWidget(name, args)
        tool_list.mount(widget)
        widget.scroll_visible()
        return widget

    def on_tool_end(self, widget: ToolCallWidget, result: str, success: bool):
        widget.update_result(result, success)
        if "IMAGE:" in result:
            self.notify("Camera snapshot captured. Click link in sidebar to view.", title="Image Captured", severity="information")