import time

import pyautogui

# Set these to the screen coordinates of the app icon in the Dock.
X_COORD = 1078
Y_COORD = 381

# Wait briefly so the user can prepare the screen.
DELAY_SECONDS = 1.5

# Use small negative steps to create a smoother downward scroll on macOS.
SCROLL_STEP = -25
SCROLL_STEPS = 20
SCROLL_PAUSE_SECONDS = 0.02


def main() -> None:
    # Pause before moving the mouse.
    time.sleep(DELAY_SECONDS)

    # Move the cursor to the target position.
    pyautogui.moveTo(X_COORD, Y_COORD)

    # Click the target position to focus the scrollable area.
    pyautogui.click()

    # Scroll down in small steps so the motion looks smoother.
    for _ in range(SCROLL_STEPS):
        pyautogui.scroll(SCROLL_STEP)
        time.sleep(SCROLL_PAUSE_SECONDS)


if __name__ == "__main__":
    main()
