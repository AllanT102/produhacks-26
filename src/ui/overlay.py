"""Lightweight native macOS status overlay."""

import math
import queue
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
    "listening": {"dot": (0.11, 0.63, 0.34), "label": "Listening", "chip": (0.90, 0.97, 0.93)},
    "processing": {"dot": (0.93, 0.56, 0.09), "label": "Thinking", "chip": (0.99, 0.94, 0.88)},
    "idle": {"dot": (0.22, 0.49, 0.91), "label": "Ready", "chip": (0.90, 0.94, 0.99)},
    "stopped": {"dot": (0.86, 0.25, 0.25), "label": "Stopped", "chip": (0.99, 0.91, 0.91)},
    "error": {"dot": (0.72, 0.19, 0.19), "label": "Error", "chip": (0.98, 0.90, 0.90)},
}


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

        width = 432.0
        height = 88.0
        frame = NSScreen.mainScreen().visibleFrame()
        x = frame.origin.x + ((frame.size.width - width) / 2.0)
        y = frame.origin.y + frame.size.height - height - 26.0

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
        content.layer().setCornerRadius_(24.0)
        content.layer().setBorderWidth_(1.0)
        content.layer().setBorderColor_(
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.83, 0.83, 0.82, 0.82).CGColor()
        )
        content.layer().setBackgroundColor_(
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.97, 0.97, 0.96, 0.94).CGColor()
        )
        self.window.setContentView_(content)
        self.content = content

        self.status_chip = NSView.alloc().initWithFrame_(NSMakeRect(18, 50, 108, 24))
        self.status_chip.setWantsLayer_(True)
        self.status_chip.layer().setCornerRadius_(12.0)
        content.addSubview_(self.status_chip)

        self.dot_halo = NSView.alloc().initWithFrame_(NSMakeRect(6, 4, 16, 16))
        self.dot_halo.setWantsLayer_(True)
        self.dot_halo.layer().setCornerRadius_(8.0)
        self.dot_halo.setAlphaValue_(0.0)
        self.status_chip.addSubview_(self.dot_halo)

        self.dot = NSView.alloc().initWithFrame_(NSMakeRect(10, 8, 8, 8))
        self.dot.setWantsLayer_(True)
        self.dot.layer().setCornerRadius_(4.0)
        self.status_chip.addSubview_(self.dot)

        self.status_label = NSTextField.alloc().initWithFrame_(NSMakeRect(24, 2, 72, 18))
        self.status_label.setBezeled_(False)
        self.status_label.setDrawsBackground_(False)
        self.status_label.setEditable_(False)
        self.status_label.setSelectable_(False)
        self.status_label.setFont_(NSFont.systemFontOfSize_(11))
        self.status_label.setTextColor_(NSColor.colorWithCalibratedWhite_alpha_(0.12, 1.0))
        self.status_chip.addSubview_(self.status_label)

        self.stop_button = NSButton.alloc().initWithFrame_(NSMakeRect(318, 48, 56, 28))
        self.stop_button.setTitle_("Stop")
        self.stop_button.setTarget_(self.delegate)
        self.stop_button.setAction_("stopClicked:")
        self.stop_button.setBordered_(False)
        self.stop_button.setWantsLayer_(True)
        self.stop_button.layer().setCornerRadius_(14.0)
        self.stop_button.layer().setBackgroundColor_(
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.95, 0.91, 0.90, 1.0).CGColor()
        )
        self.stop_button.setFont_(NSFont.boldSystemFontOfSize_(12))
        self.stop_button.setContentTintColor_(
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.61, 0.18, 0.16, 1.0)
        )
        content.addSubview_(self.stop_button)

        self.quit_button = NSButton.alloc().initWithFrame_(NSMakeRect(380, 48, 32, 28))
        self.quit_button.setTitle_("x")
        self.quit_button.setTarget_(self.delegate)
        self.quit_button.setAction_("quitClicked:")
        self.quit_button.setBordered_(False)
        self.quit_button.setWantsLayer_(True)
        self.quit_button.layer().setCornerRadius_(14.0)
        self.quit_button.layer().setBackgroundColor_(
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.92, 0.92, 0.91, 1.0).CGColor()
        )
        self.quit_button.setFont_(NSFont.boldSystemFontOfSize_(14))
        self.quit_button.setContentTintColor_(
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.35, 0.35, 0.35, 1.0)
        )
        content.addSubview_(self.quit_button)

        self.transcript_label = NSTextField.alloc().initWithFrame_(NSMakeRect(18, 22, 340, 24))
        self.transcript_label.setBezeled_(False)
        self.transcript_label.setDrawsBackground_(False)
        self.transcript_label.setEditable_(False)
        self.transcript_label.setSelectable_(False)
        self.transcript_label.setFont_(NSFont.systemFontOfSize_(15))
        self.transcript_label.setTextColor_(NSColor.colorWithCalibratedWhite_alpha_(0.07, 1.0))
        self.transcript_label.setLineBreakMode_(4)
        content.addSubview_(self.transcript_label)

        self.placeholder_label = NSTextField.alloc().initWithFrame_(NSMakeRect(18, 22, 250, 20))
        self.placeholder_label.setBezeled_(False)
        self.placeholder_label.setDrawsBackground_(False)
        self.placeholder_label.setEditable_(False)
        self.placeholder_label.setSelectable_(False)
        self.placeholder_label.setFont_(NSFont.systemFontOfSize_(15))
        self.placeholder_label.setTextColor_(NSColor.colorWithCalibratedWhite_alpha_(0.55, 1.0))
        self.placeholder_label.setStringValue_("Say a command")
        content.addSubview_(self.placeholder_label)

        self.detail_label = NSTextField.alloc().initWithFrame_(NSMakeRect(140, 54, 180, 16))
        self.detail_label.setBezeled_(False)
        self.detail_label.setDrawsBackground_(False)
        self.detail_label.setEditable_(False)
        self.detail_label.setSelectable_(False)
        self.detail_label.setFont_(NSFont.systemFontOfSize_(11))
        self.detail_label.setTextColor_(NSColor.colorWithCalibratedWhite_alpha_(0.42, 1.0))
        content.addSubview_(self.detail_label)

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
            self.state.detail = event.payload.get("detail", self.state.detail)

        self.refresh_ui()

    def refresh_ui(self) -> None:
        """Render the current overlay state."""
        style = STATUS_STYLES.get(self.state.status, STATUS_STYLES["idle"])
        red, green, blue = style["dot"]
        chip_red, chip_green, chip_blue = style["chip"]
        self.status_chip.layer().setBackgroundColor_(
            NSColor.colorWithCalibratedRed_green_blue_alpha_(chip_red, chip_green, chip_blue, 1.0).CGColor()
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
        self.detail_label.setStringValue_(self.state.detail)
        self._update_animation()

    def _update_animation(self) -> None:
        """Pulse the status indicator while the agent is active."""
        if self.state.status == "processing":
            phase = (math.sin(self._pulse_tick / 2.4) + 1.0) / 2.0
            scale = 14.0 + (phase * 6.0)
            origin = 8.0 - ((scale - 16.0) / 2.0)
            self.dot_halo.setFrame_(NSMakeRect(origin, origin, scale, scale))
            self.dot_halo.layer().setCornerRadius_(scale / 2.0)
            self.dot_halo.setAlphaValue_(0.28 + (phase * 0.22))
        else:
            self.dot_halo.setAlphaValue_(0.0)
