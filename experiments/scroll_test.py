import time

from src.tool_runtime.tools.scroll import scroll

# Set these to the screen coordinates of the area you want to scroll.
X_COORD = 760
Y_COORD = 400

# Wait so you can focus the right window before scrolling starts.
DELAY_SECONDS = 3


def main() -> None:
    time.sleep(DELAY_SECONDS)

    print("Scrolling down...")
    result = scroll(X_COORD, Y_COORD, direction="down", amount=10)
    print(result)

    time.sleep(1)

    print("Scrolling up...")
    result = scroll(X_COORD, Y_COORD, direction="up", amount=10)
    print(result)


if __name__ == "__main__":
    main()
