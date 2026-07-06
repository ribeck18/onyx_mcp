from onyx import mcp
import projects
import transfers
import vdi


def main():
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
