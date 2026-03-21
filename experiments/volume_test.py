from src.tool_runtime.tools.volume import set_volume


def main() -> None:
    print(set_volume("up"))           # +10
    print(set_volume("up", steps=3))  # +30
    print(set_volume("down"))         # -10
    print(set_volume("mute"))
    print(set_volume("unmute"))


if __name__ == "__main__":
    main()
