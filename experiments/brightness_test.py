from src.tool_runtime.tools.brightness import set_brightness


def main() -> None:
    print(set_brightness("up"))           # +1 step
    # print(set_brightness("up", steps=3))  # +3 steps
    # print(set_brightness("down", steps=2))


if __name__ == "__main__":
    main()
