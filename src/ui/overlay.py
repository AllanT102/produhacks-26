"""Lightweight native macOS status overlay."""

import math
import queue
import time
from dataclasses import dataclass
from typing import Callable

from src.shared.events import UIEvent

try:
    import objc
    from AppKit import (
        NSApp,
        NSApplication,
        NSApplicationActivationPolicyRegular,
        NSBackingStoreBuffered,
        NSButton,
        NSColor,
        NSFont,
        NSMakeRect,
        NSRunningApplication,
        NSScreen,
        NSTextField,
        NSView,
        NSWindow,
        NSWindowStyleMaskBorderless,
    )
    from Foundation import NSObject, NSTimer
except ImportError as exc:
    raise RuntimeError(
        "PyObjC is required for the desktop overlay. Install requirements.txt again."
    ) from exc


STATUS_STYLES = {
    "listening": {
        "dot": (0.46, 0.86, 0.73),
        "line": (0.46, 0.86, 0.73),
        "label": "Listening",
        "chip": (0.24, 0.37, 0.33),
        "chip_alpha": 0.62,
    },
    "processing": {
        "dot": (0.57, 0.76, 0.99),
        "line": (0.64, 0.78, 1.00),
        "label": "Working",
        "chip": (0.24, 0.31, 0.40),
        "chip_alpha": 0.68,
    },
    "idle": {
        "dot": (0.56, 0.72, 0.96),
        "line": (0.56, 0.72, 0.96),
        "label": "Ready",
        "chip": (0.24, 0.29, 0.37),
        "chip_alpha": 0.58,
    },
    "stopped": {
        "dot": (0.97, 0.63, 0.45),
        "line": (0.97, 0.63, 0.45),
        "label": "Stopped",
        "chip": (0.38, 0.29, 0.26),
        "chip_alpha": 0.7,
    },
    "error": {
        "dot": (1.00, 0.44, 0.44),
        "line": (1.00, 0.44, 0.44),
        "label": "Error",
        "chip": (0.41, 0.23, 0.23),
        "chip_alpha": 0.76,
    },
}

PROCESSING_GLYPHS = ["·", "✢", "✳", "✶", "✻", "✽"]
PROCESSING_WORDS = [
    "Tinkering",
    "Thinking",
    "Reticulating",
    "Pondering",
    "Crafting",
    "Working",
]


@dataclass
class OverlayState:
    status: str = "listening"
    transcript: str = ""
    detail: str = "Mic live"


class OverlayDelegate(NSObject):
    """Objective-C bridge for timer and button callbacks."""

    def initWithOverlay_(self, overlay):
        self = objc.super(OverlayDelegate, self).init()
        if self is None:
            return None
        self.overlay = overlay
        return self

    def poll_(self, _timer) -> None:
        self.overlay.poll_events()

    def stopClicked_(self, _sender) -> None:
        self.overlay.on_stop()

    def quitClicked_(self, _sender) -> None:
        self.overlay.on_quit()
        NSApp().terminate_(None)

    def windowWillClose_(self, _notification) -> None:
        NSApp().terminate_(None)


class VoiceOverlay:
    """Small always-visible control surface for app state."""

    def __init__(
        self,
        event_queue: "queue.Queue[UIEvent]",
        on_stop: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self.event_queue = event_queue
        self.on_stop = on_stop
        self.on_quit = on_quit
        self.state = OverlayState()

        self.app = NSApplication.sharedApplication()
        self.app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        self._pulse_tick = 0
        self._last_activity_at = time.time()
        self._compact_size = (156.0, 40.0)
        self._expanded_size = (468.0, 108.0)
        self._expanded = False
        self._processing_active = False
        self._processing_glyph_index = 0
        self._processing_glyph_direction = 1
        self._processing_word_index = 0

        width, height = self._compact_size
        frame = NSScreen.mainScreen().visibleFrame()
        x = frame.origin.x + ((frame.size.width - width) / 2.0)
        y = frame.origin.y + frame.size.height - height - 22.0

        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, width, height),
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        self.window.setReleasedWhenClosed_(False)
        self.window.setLevel_(3)
        self.window.setOpaque_(False)
        self.window.setHasShadow_(True)
        self.window.setMovableByWindowBackground_(True)
        self.window.setBackgroundColor_(NSColor.clearColor())

        self.delegate = OverlayDelegate.alloc().initWithOverlay_(self)
        self.window.setDelegate_(self.delegate)

        content = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, width, height))
        content.setWantsLayer_(True)
        content.layer().setCornerRadius_(20.0)
        content.layer().setBorderWidth_(1.0)
        content.layer().setBorderColor_(
            NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.10).CGColor()
        )
        content.layer().setBackgroundColor_(
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.11, 0.11, 0.13, 0.82).CGColor()
        )
        self.window.setContentView_(content)
        self.content = content

        self.activity_glow = NSView.alloc().initWithFrame_(NSMakeRect(48, height - 8, 72, 3))
        self.activity_glow.setWantsLayer_(True)
        self.activity_glow.layer().setCornerRadius_(1.5)
        self.activity_glow.setAlphaValue_(0.0)
        content.addSubview_(self.activity_glow)

        self.status_chip = NSView.alloc().initWithFrame_(NSMakeRect(16, 8, 112, 24))
        self.status_chip.setWantsLayer_(True)
        self.status_chip.layer().setCornerRadius_(12.0)
        self.status_chip.layer().setBorderWidth_(1.0)
        self.status_chip.layer().setBorderColor_(
            NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.06).CGColor()
        )
        content.addSubview_(self.status_chip)

        self.dot_halo = NSView.alloc().initWithFrame_(NSMakeRect(7, 4, 16, 16))
        self.dot_halo.setWantsLayer_(True)
        self.dot_halo.layer().setCornerRadius_(8.0)
        self.dot_halo.setAlphaValue_(0.0)
        self.status_chip.addSubview_(self.dot_halo)

        self.dot = NSView.alloc().initWithFrame_(NSMakeRect(11, 8, 8, 8))
        self.dot.setWantsLayer_(True)
        self.dot.layer().setCornerRadius_(4.0)
        self.status_chip.addSubview_(self.dot)

        self.status_label = NSTextField.alloc().initWithFrame_(NSMakeRect(28, 2, 76, 18))
        self.status_label.setBezeled_(False)
        self.status_label.setDrawsBackground_(False)
        self.status_label.setEditable_(False)
        self.status_label.setSelectable_(False)
        self.status_label.setFont_(NSFont.boldSystemFontOfSize_(11))
        self.status_label.setTextColor_(NSColor.colorWithCalibratedWhite_alpha_(0.96, 1.0))
        self.status_chip.addSubview_(self.status_label)

        self.stop_button = NSButton.alloc().initWithFrame_(NSMakeRect(346, 66, 70, 28))
        self.stop_button.setTitle_("Stop")
        self.stop_button.setTarget_(self.delegate)
        self.stop_button.setAction_("stopClicked:")
        self.stop_button.setBordered_(False)
        self.stop_button.setWantsLayer_(True)
        self.stop_button.layer().setCornerRadius_(14.0)
        self.stop_button.layer().setBorderWidth_(1.0)
        self.stop_button.layer().setBorderColor_(
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.86, 0.47, 0.43, 0.20).CGColor()
        )
        self.stop_button.layer().setBackgroundColor_(
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.55, 0.18, 0.15, 0.18).CGColor()
        )
        self.stop_button.setFont_(NSFont.boldSystemFontOfSize_(12))
        self.stop_button.setContentTintColor_(
            NSColor.colorWithCalibratedWhite_alpha_(0.98, 0.95)
        )
        content.addSubview_(self.stop_button)

        self.quit_button = NSButton.alloc().initWithFrame_(NSMakeRect(424, 66, 28, 28))
        self.quit_button.setTitle_("x")
        self.quit_button.setTarget_(self.delegate)
        self.quit_button.setAction_("quitClicked:")
        self.quit_button.setBordered_(False)
        self.quit_button.setWantsLayer_(True)
        self.quit_button.layer().setCornerRadius_(14.0)
        self.quit_button.layer().setBorderWidth_(1.0)
        self.quit_button.layer().setBorderColor_(
            NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.06).CGColor()
        )
        self.quit_button.layer().setBackgroundColor_(
            NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.06).CGColor()
        )
        self.quit_button.setFont_(NSFont.boldSystemFontOfSize_(14))
        self.quit_button.setContentTintColor_(
            NSColor.colorWithCalibratedWhite_alpha_(0.82, 1.0)
        )
        content.addSubview_(self.quit_button)

        self.transcript_label = NSTextField.alloc().initWithFrame_(NSMakeRect(22, 24, 404, 28))
        self.transcript_label.setBezeled_(False)
        self.transcript_label.setDrawsBackground_(False)
        self.transcript_label.setEditable_(False)
        self.transcript_label.setSelectable_(False)
        self.transcript_label.setFont_(NSFont.systemFontOfSize_(19))
        self.transcript_label.setTextColor_(NSColor.colorWithCalibratedWhite_alpha_(0.97, 1.0))
        self.transcript_label.setLineBreakMode_(4)
        content.addSubview_(self.transcript_label)

        self.placeholder_label = NSTextField.alloc().initWithFrame_(NSMakeRect(22, 24, 260, 22))
        self.placeholder_label.setBezeled_(False)
        self.placeholder_label.setDrawsBackground_(False)
        self.placeholder_label.setEditable_(False)
        self.placeholder_label.setSelectable_(False)
        self.placeholder_label.setFont_(NSFont.systemFontOfSize_(17))
        self.placeholder_label.setTextColor_(NSColor.colorWithCalibratedWhite_alpha_(0.42, 1.0))
        self.placeholder_label.setStringValue_("Say a command")
        content.addSubview_(self.placeholder_label)

        self.detail_label = NSTextField.alloc().initWithFrame_(NSMakeRect(146, 70, 188, 16))
        self.detail_label.setBezeled_(False)
        self.detail_label.setDrawsBackground_(False)
        self.detail_label.setEditable_(False)
        self.detail_label.setSelectable_(False)
        self.detail_label.setFont_(self._monospaced_font(11, bold=False))
        self.detail_label.setTextColor_(NSColor.colorWithCalibratedWhite_alpha_(0.56, 1.0))
        content.addSubview_(self.detail_label)

        self.detail_symbol_label = NSTextField.alloc().initWithFrame_(NSMakeRect(146, 69, 16, 16))
        self.detail_symbol_label.setBezeled_(False)
        self.detail_symbol_label.setDrawsBackground_(False)
        self.detail_symbol_label.setEditable_(False)
        self.detail_symbol_label.setSelectable_(False)
        self.detail_symbol_label.setFont_(self._monospaced_font(13, bold=True))
        self.detail_symbol_label.setTextColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(0.88, 0.68, 0.53, 1.0))
        self.detail_symbol_label.setHidden_(True)
        content.addSubview_(self.detail_symbol_label)

        self.refresh_ui()
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.08,
            self.delegate,
            "poll:",
            None,
            True,
        )

    def run(self) -> None:
        """Start the overlay event loop."""
        self.window.makeKeyAndOrderFront_(None)
        NSRunningApplication.currentApplication().activateWithOptions_(1)
        self.app.run()

    def close(self) -> None:
        """Destroy the overlay window."""
        if self.timer is not None:
            self.timer.invalidate()
        self.window.close()

    def poll_events(self) -> None:
        """Apply queued UI events."""
        self._pulse_tick += 1
        while True:
            try:
                event = self.event_queue.get_nowait()
            except queue.Empty:
                break
            self.handle_event(event)
        self._maybe_compact()
        self._update_animation()

    def handle_event(self, event: UIEvent) -> None:
        """Update visible state from an incoming event."""
        if event.type == "transcript":
            self.state.transcript = event.payload.get("text", self.state.transcript) or "..."
            transcript_type = event.payload.get("kind", "partial")
            if transcript_type == "partial":
                self.state.detail = "Listening..."
                if self.state.status != "processing":
                    self.state.status = "listening"
            else:
                self.state.detail = "Command captured"
        elif event.type == "agent_status":
            self.state.status = event.payload.get("state", self.state.status)
            self.state.detail = event.payload.get("step") or event.payload.get("detail", self.state.detail)

        self._last_activity_at = time.time()
        self.refresh_ui()

    def refresh_ui(self) -> None:
        """Render the current overlay state."""
        style = STATUS_STYLES.get(self.state.status, STATUS_STYLES["idle"])
        red, green, blue = style["dot"]
        chip_red, chip_green, chip_blue = style["chip"]
        self.status_chip.layer().setBackgroundColor_(
            NSColor.colorWithCalibratedRed_green_blue_alpha_(
                chip_red,
                chip_green,
                chip_blue,
                style.get("chip_alpha", 0.6),
            ).CGColor()
        )
        self.dot.layer().setBackgroundColor_(
            NSColor.colorWithCalibratedRed_green_blue_alpha_(red, green, blue, 1.0).CGColor()
        )
        self.dot_halo.layer().setBackgroundColor_(
            NSColor.colorWithCalibratedRed_green_blue_alpha_(red, green, blue, 0.18).CGColor()
        )
        self.status_label.setStringValue_(style["label"])
        self.transcript_label.setStringValue_(self.state.transcript)
        self.placeholder_label.setHidden_(bool(self.state.transcript))
        self.transcript_label.setHidden_(not bool(self.state.transcript))
        self._apply_detail_copy()
        self._apply_layout()
        self._update_animation()

    def _update_animation(self) -> None:
        """Animate a restrained activity line and status halo."""
        style = STATUS_STYLES.get(self.state.status, STATUS_STYLES["idle"])
        line_red, line_green, line_blue = style["line"]
        content_width = self.content.frame().size.width
        content_height = self.content.frame().size.height
        if self.state.status == "processing":
            self._advance_processing_status()
            phase = (math.sin(self._pulse_tick / 2.4) + 1.0) / 2.0
            scale = 14.0 + (phase * 4.0)
            origin = 8.0 - ((scale - 16.0) / 2.0)
            self.dot_halo.setFrame_(NSMakeRect(origin, origin, scale, scale))
            self.dot_halo.layer().setCornerRadius_(scale / 2.0)
            self.dot_halo.setAlphaValue_(0.24 + (phase * 0.16))
            width = 88.0 + (phase * 40.0)
            sweep = ((self._pulse_tick % 120) / 120.0)
            x = 22.0 + (sweep * max(1.0, content_width - 44.0 - width))
            self.activity_glow.setFrame_(NSMakeRect(x, content_height - 8.0, width, 3.0))
            self.activity_glow.layer().setCornerRadius_(1.5)
            self.activity_glow.layer().setBackgroundColor_(
                NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    line_red,
                    line_green,
                    line_blue,
                    0.88,
                ).CGColor()
            )
            self.activity_glow.setAlphaValue_(0.52 + (phase * 0.18))
        else:
            self._processing_active = False
            self.dot_halo.setAlphaValue_(0.0)
            if self._expanded:
                width = 74.0
                self.activity_glow.setFrame_(
                    NSMakeRect((content_width - width) / 2.0, content_height - 8.0, width, 3.0)
                )
                self.activity_glow.layer().setCornerRadius_(1.5)
                self.activity_glow.layer().setBackgroundColor_(
                    NSColor.colorWithCalibratedRed_green_blue_alpha_(
                        line_red,
                        line_green,
                        line_blue,
                        0.45,
                    ).CGColor()
                )
                self.activity_glow.setAlphaValue_(0.16)
            else:
                self.activity_glow.setAlphaValue_(0.0)

    def _is_expanded_state(self) -> bool:
        """Return whether the overlay should be expanded."""
        return self.state.status in ("processing", "stopped", "error") or bool(self.state.transcript)

    def _maybe_compact(self) -> None:
        """Collapse the overlay after a brief quiet period."""
        if self.state.status in ("processing", "stopped", "error"):
            return
        if self.state.transcript and (time.time() - self._last_activity_at) > 2.6:
            self.state.transcript = ""
            self.state.detail = "Mic live"
            self.refresh_ui()

    def _apply_layout(self) -> None:
        """Switch between subtle idle pill and expanded action card."""
        expanded = self._is_expanded_state()
        if expanded != self._expanded:
            self._expanded = expanded
            width, height = self._expanded_size if expanded else self._compact_size
            self._resize_window(width, height, expanded)

        if expanded:
            self.status_chip.setFrame_(NSMakeRect(18, 66, 114, 24))
            self.detail_symbol_label.setFrame_(NSMakeRect(146, 69, 16, 16))
            self.detail_label.setFrame_(NSMakeRect(146, 70, 188, 16))
            self.stop_button.setFrame_(NSMakeRect(346, 66, 70, 28))
            self.quit_button.setFrame_(NSMakeRect(424, 66, 28, 28))
            self.stop_button.setHidden_(self.state.status != "processing")
            self.quit_button.setHidden_(False)
            self.detail_label.setHidden_(False)
            self.placeholder_label.setHidden_(bool(self.state.transcript))
            self.transcript_label.setFrame_(NSMakeRect(22, 24, 404, 28))
            self.placeholder_label.setFrame_(NSMakeRect(22, 24, 260, 22))
        else:
            self.status_chip.setFrame_(NSMakeRect(20, 8, 112, 24))
            self.stop_button.setHidden_(True)
            self.quit_button.setHidden_(True)
            self.detail_label.setHidden_(True)
            self.detail_symbol_label.setHidden_(True)
            self.placeholder_label.setHidden_(True)
            self.transcript_label.setHidden_(True)

    def _resize_window(self, width: float, height: float, expanded: bool) -> None:
        """Resize and reposition the floating overlay."""
        frame = NSScreen.mainScreen().visibleFrame()
        x = frame.origin.x + ((frame.size.width - width) / 2.0)
        y = frame.origin.y + frame.size.height - height - (26.0 if expanded else 22.0)
        self.window.setFrame_display_animate_(NSMakeRect(x, y, width, height), True, True)
        self.content.setFrame_(NSMakeRect(0, 0, width, height))

    def _apply_detail_copy(self) -> None:
        """Render the compact status copy or the Claude-like processing phrase."""
        if self.state.status == "processing":
            self.detail_symbol_label.setHidden_(False)
            self.detail_symbol_label.setStringValue_(PROCESSING_GLYPHS[self._processing_glyph_index])
            self.detail_label.setStringValue_(PROCESSING_WORDS[self._processing_word_index] + "…")
            self.detail_label.setTextColor_(NSColor.colorWithCalibratedWhite_alpha_(0.70, 1.0))
            self.detail_label.setFrame_(NSMakeRect(164, 70, 170, 16))
            return

        self.detail_symbol_label.setHidden_(True)
        self.detail_label.setStringValue_(self.state.detail)
        self.detail_label.setTextColor_(NSColor.colorWithCalibratedWhite_alpha_(0.56, 1.0))
        self.detail_label.setFrame_(NSMakeRect(146, 70, 188, 16))

    def _advance_processing_status(self) -> None:
        """Cycle the Claude-like glyph spinner and slower verb changes."""
        if not self._processing_active:
            self._processing_active = True
            self._processing_glyph_index = 0
            self._processing_glyph_direction = 1
            self._processing_word_index = 0

        if self._pulse_tick % 3 == 0:
            next_index = self._processing_glyph_index + self._processing_glyph_direction
            if next_index >= len(PROCESSING_GLYPHS) - 1 or next_index <= 0:
                self._processing_glyph_direction *= -1
                next_index = self._processing_glyph_index + self._processing_glyph_direction
            self._processing_glyph_index = max(0, min(len(PROCESSING_GLYPHS) - 1, next_index))

        if self._pulse_tick % 64 == 0:
            self._processing_word_index = (self._processing_word_index + 1) % len(PROCESSING_WORDS)

        self._apply_detail_copy()

    @staticmethod
    def _monospaced_font(size: float, bold: bool) -> object:
        """Return a monospaced system font when available."""
        weight = 0.4 if bold else 0.0
        if hasattr(NSFont, "monospacedSystemFontOfSize_weight_"):
            return NSFont.monospacedSystemFontOfSize_weight_(size, weight)
        if bold:
            return NSFont.boldSystemFontOfSize_(size)
        return NSFont.systemFontOfSize_(size)
