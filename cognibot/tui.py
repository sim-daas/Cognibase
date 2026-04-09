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
from textual.widgets import Footer, Header, Input, Static

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
        self.history = history or []
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
            with VerticalScroll(id="sidebar"):
                yield Static("ACTIVE CONTEXT", classes="sidebar-title")
                yield Static(f"Model: [dim]{self.deps.config.llm_model}[/dim]")
                yield Static("\nMODIFIED TOOLS", classes="sidebar-title")
                yield Vertical(id="tool-calls-list")


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
        self.run_agent(user_text)

    def add_message(self, role: str, content: str, is_thinking: bool = False) -> MessageWidget:
        chat_area = self.query_one("#chat-area")
        widget = MessageWidget(role, content, is_thinking)
        chat_area.mount(widget)
        widget.scroll_visible()
        return widget

    @work(exclusive=True)
    async def run_agent(self, user_input: str) -> None:
        chat_area = self.query_one("#chat-area")
        
        response_text = ""
        response_widget = None

        try:
            async with self.agent.run_stream(
                user_input,
                deps=self.deps,
                message_history=self.history if self.history else None,
                model_settings={"extra_body": {"think": "high"}},
            ) as result:
                
                # PydanticAI models sometimes strip out <think> tags natively, or chunk them weirdly.
                # Use a buffer to catch "<think>" across split chunks
                buffer = ""
                in_think = False
                thinking_text = ""
                
                async for chunk in result.stream_text(delta=True):
                    buffer += chunk
                    
                    # We process based on the buffer content
                    if not in_think:
                        if "<think>" in buffer:
                            parts = buffer.split("<think>", 1)
                            # Content before <think> belongs to early response text (usually none)
                            if parts[0]:
                                if not response_widget:
                                    response_widget = self.add_message("bot", "")
                                response_text += parts[0]
                                response_widget.content = response_text
                                response_widget.refresh()
                            
                            in_think = True
                            buffer = parts[1] # Keep the rest as thinking text
                        else:
                            # Not found yet, keep buffering if it ends in a partial tag
                            if buffer.endswith("<") or buffer.endswith("<t") or buffer.endswith("<th") or buffer.endswith("<thi") or buffer.endswith("<thin") or buffer.endswith("<think") or buffer.endswith("<think>"):
                                pass # Wait for next chunk
                            else:
                                if not response_widget:
                                    response_widget = self.add_message("bot", "")
                                response_text += buffer
                                response_widget.content = response_text
                                response_widget.refresh()
                                buffer = ""
                    
                    if in_think:
                        if "</think>" in buffer:
                            parts = buffer.split("</think>", 1)
                            thinking_text += parts[0]
                            
                            in_think = False
                            buffer = parts[1] # Keep the rest as regular response text
                            if buffer:
                                if not response_widget:
                                    response_widget = self.add_message("bot", "")
                                response_text += buffer
                                response_widget.content = response_text
                                response_widget.refresh()
                                buffer = ""
                        else:
                            # Might be partial closing tag
                            if buffer.endswith("<") or buffer.endswith("</") or buffer.endswith("</t") or buffer.endswith("</th") or buffer.endswith("</thi") or buffer.endswith("</thin") or buffer.endswith("</think") or buffer.endswith("</think>"):
                                pass # Wait for next chunk
                            else:
                                thinking_text += buffer
                                buffer = ""

                # Flush any remaining buffer
                if buffer:
                    if in_think:
                        thinking_text += buffer
                    else:
                        if not response_widget:
                            response_widget = self.add_message("bot", "")
                        response_text += buffer
                        response_widget.content = response_text
                        response_widget.refresh()
                
                self.history.extend(result.new_messages())
                
        except Exception as e:
            self.add_message("system", f"Error: {str(e)}")

    # ── Tool Call Hooks ──────────────────────────────────────────────

    def on_tool_start(self, name: str, args: dict) -> ToolCallWidget:
        tool_list = self.query_one("#tool-calls-list")
        widget = ToolCallWidget(name, args)
        tool_list.mount(widget)
        return widget

    def on_tool_end(self, widget: ToolCallWidget, result: str, success: bool):
        widget.update_result(result, success)