import time

from src.tool_runtime.tools.keyboard import type_text

# Wait so you can click into a text field before typing starts.
DELAY_SECONDS = 3


def main() -> None:
    time.sleep(DELAY_SECONDS)

    # print("Typing text...")
    # result = type_text("hello world")
    # print(result)

    # time.sleep(2)

    print("Typing with clear_first...")
    result = type_text("this replaced everything", clear_first=True)
    print(result)


if __name__ == "__main__":
    main()
