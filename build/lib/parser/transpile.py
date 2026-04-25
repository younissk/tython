import argparse
import ast
from pathlib import Path

from .core import lower, parse_custom


def main() -> None:
    argparser = argparse.ArgumentParser()
    argparser.add_argument("input", help="Path to input .ty source")
    argparser.add_argument("output", help="Path to output .py file")
    args = argparser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if input_path.suffix != ".ty":
        raise SystemExit("transpile currently supports .ty inputs only")

    source = input_path.read_text()
    lowered = lower(parse_custom(source))
    output_path.write_text(ast.unparse(lowered) + "\n")
    print(output_path)


if __name__ == "__main__":
    main()
