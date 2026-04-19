import argparse
import ast
from pathlib import Path

from .core import lower, parse_custom, parse_file


def main() -> None:
    argparser = argparse.ArgumentParser()
    argparser.add_argument("filename")
    argparser.add_argument("--mode", choices=["exec", "eval", "single"], default="exec")
    argparser.add_argument(
        "--transpile",
        action="store_true",
        help="Transpile .txt custom syntax to a .py file instead of executing it.",
    )
    argparser.add_argument(
        "-o",
        "--output",
        help="Output path for --transpile (defaults to input path with .py suffix).",
    )
    args = argparser.parse_args()

    file_path = Path(args.filename)

    if args.transpile:
        if file_path.suffix != ".txt":
            raise SystemExit("--transpile currently supports .txt inputs only")

        source = file_path.read_text()
        lowered = lower(parse_custom(source))
        output_path = Path(args.output) if args.output else file_path.with_suffix(".py")
        output_path.write_text(ast.unparse(lowered) + "\n")
        print(output_path)
        return

    if file_path.suffix == ".txt":
        source = file_path.read_text()
        lowered = lower(parse_custom(source))
        code = compile(lowered, str(file_path), args.mode)

        if args.mode == "eval":
            print(eval(code, {"__name__": "__main__"}))
        else:
            exec(code, {"__name__": "__main__"})
        return

    tree = parse_file(file_path, mode=args.mode)
    print(ast.dump(tree, indent=2))
