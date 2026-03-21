from src.tool_runtime.tools.app import open_app


def main() -> None:
    print(open_app("chrome"))
    print(open_app("spotify"))
    print(open_app("discord"))


if __name__ == "__main__":
    main()
