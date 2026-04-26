# Error Code Catalog

Schema version: `1`

This catalog is generated from the parser source. The source location is the canonical
reference for behavior and wording.

## Validation and project errors

| Code | Area | Source | Summary |
| --- | --- | --- | --- |
| `E1001` | parse | `parser/custom_frontend/rewriters_structured.py:105` | err( "E1001", lineno, f"{maybe_binding.group('kind')} binding '{maybe_binding.group('name')}'... |
| `E1002` | parse | `parser/custom_frontend/type_system.py:11` | err( "E1002", lineno, "empty type annotation", "Provide a concrete type name.", ) |
| `E1003` | parse | `parser/custom_frontend/type_system.py:24` | err( "E1003", lineno, f"invalid type annotation '{type_expr}'", "Unexpected trailing tokens i... |
| `E1004` | parse | `parser/custom_frontend/type_system.py:174` | err( "E1004", self.lineno, f"invalid type annotation '{self.text}'", "Reserved keywords canno... |
| `E1005` | parse | `parser/custom_frontend/rewriters_brace.py:50` | err("E1005", lineno, "unmatched '}'", "Remove extra closing brace.") |
| `E1006` | parse | `parser/custom_frontend/rewriters_brace.py:69` | err( "E1006", lineno, "`function` keyword is not supported", "Use `func` for function declara... |
| `E1007` | parse | `parser/custom_frontend/rewriters_brace.py:286` | err( "E1007", len(lines) or 1, "unclosed '{' block", "Close every opened block with '}'.", ) |
| `E1008` | parse | `parser/custom_frontend/functions.py:29` | err( "E1008", lineno, "invalid expression-bodied function declaration", "Use `func name(param... |
| `E1009` | parse | `parser/custom_frontend/functions.py:64` | err( "E1009", lineno, "invalid function name in declaration", "Use `func name(...) -> Type`.", ) |
| `E1010` | parse | `parser/custom_frontend/functions.py:77` | err( "E1010", lineno, "function parameters must be enclosed in ()", "Add `( ... )` after func... |
| `E1011` | parse | `parser/custom_frontend/functions.py:91` | err( "E1011", lineno, "function return type is required", "Add `-> Type` in function declarat... |
| `E1012` | parse | `parser/custom_frontend/functions.py:102` | err( "E1012", lineno, "function return type is missing", "Specify a return type after `->`.", ) |
| `E1013` | parse | `parser/custom_frontend/rewriters_structured.py:51` | err( "E1013", i + 1, f"invalid enum member {member_name!r} in enum {enum_name}", "Enum member... |
| `E1014` | parse | `parser/custom_frontend/rewriters_structured.py:63` | err( "E1014", i + 1, f"enum {enum_name} must declare at least one member", "Add one or more e... |
| `E1015` | parse | `parser/custom_frontend/helpers.py:67` | err( "E1015", 1, f"unmatched '{opener}'", f"Ensure every `{opener}` has a matching `{closer}`... |
| `E1016` | parse | `parser/custom_frontend/rewriters_brace.py:55` | err( "E1016", closed.lineno, "empty block is not allowed", "Use `pass` for intentionally empt... |
| `E1017` | parse | `parser/custom_frontend/rewriters_ternary.py:57` | err( "E1017", lineno, "invalid ternary syntax", "Use `if cond: expr else expr`.", ) |
| `E1018` | parse | `parser/custom_frontend/rewriters_ternary.py:34` | err( "E1018", lineno, "ternary used as operator subexpression must be parenthesized", "Wrap t... |
| `E1021` | parse | `parser/custom_frontend/rewriters_brace.py:79` | err( "E1021", lineno, "inheritance is not supported in v1", "Use records + class conformance... |
| `E1022` | parse | `parser/custom_frontend/rewriters_brace.py:136` | err( "E1022", lineno, "invalid record member", "Use `name: Type` fields only inside records.", ) |
| `E1023` | parse | `parser/custom_frontend/rewriters_brace.py:156` | err( "E1023", lineno, "`setup` cannot be marked pub", "Use bare `setup { ... }`.", ) |
| `E1024` | parse | `parser/custom_frontend/rewriters_brace.py:165` | err( "E1024", lineno, "invalid setup declaration", "Use `setup { ... }` with no parameters an... |
| `E1025` | parse | `parser/custom_frontend/rewriters_brace.py:311` | err( "E1025", lineno, "init fields are already public and cannot use `pub`", "Use `init var .... |
| `E1026` | parse | `parser/custom_frontend/rewriters_misc.py:79` | err( "E1026", i + 1, "invalid record literal field", "Use `field: expression` entries inside... |
| `E1027` | parse | `parser/custom_frontend/rewriters_misc.py:101` | err( "E1027", len(lines), "unclosed record literal block", "Close record literals with `}`.", ) |
| `E1028` | parse | `parser/custom_frontend/rewriters_brace.py:346` | err( "E1028", lineno, "catch requires binding name", "Use `catch err { ... }` or `catch err:... |
| `E2001` | typecheck | `parser/semantics/checker.py:101` | err("E2001", 1, "custom parser expects module input") |
| `E2002` | typecheck | `parser/semantics/checker.py:226` | err( "E2002", stmt.lineno, "only simple name assignment or `this.member` assignment is suppor... |
| `E2003` | typecheck | `parser/semantics/checker.py:237` | err( "E2003", stmt.lineno, "only simple name annotations are supported", "Use `name: Type` or... |
| `E2004` | typecheck | `parser/semantics/checker.py:246` | err( "E2004", stmt.lineno, "standalone annotations are not valid runtime assignments", "Use `... |
| `E2005` | typecheck | `parser/semantics/checker.py:368` | err( "E2005", getattr(stmt, "lineno", 1), f"unsupported statement {type(stmt).__name__}", "Us... |
| `E2008` | typecheck | `parser/semantics/checker.py:1752` | err( "E2008", lineno, "only simple loop variables are supported", "Use a single identifier lo... |
| `E2009` | typecheck | `parser/semantics/checker.py:1824` | err( "E2009", expr.lineno, "mixed-type list literal is not supported", "Use elements of one c... |
| `E2010` | typecheck | `parser/semantics/checker.py:2018` | err( "E2010", getattr(expr, "lineno", 1), f"unsupported expression {type(expr).__name__}", "U... |
| `E2011` | typecheck | `parser/semantics/checker.py:3095` | err( "E2011", lineno, f"reserved word '{decl.name}' cannot be used as an identifier", "Choose... |
| `E2012` | typecheck | `parser/semantics/checker.py:3104` | err( "E2012", lineno, f"invalid identifier '{decl.name}'", "Use letters, digits, or underscor... |
| `E2013` | typecheck | `parser/semantics/checker.py:3114` | err( "E2013", lineno, f"invalid const name '{decl.name}'", "Use UPPER_SNAKE_CASE for const bi... |
| `E2014` | typecheck | `parser/semantics/checker.py:3123` | err( "E2014", lineno, f"invalid var name '{decl.name}'", "Use snake_case for var bindings.", ) |
| `E2015` | typecheck | `parser/semantics/checker.py:3133` | err( "E2015", lineno, f"binding '{decl.name}' without initializer requires a type annotation"... |
| `E2016` | typecheck | `parser/semantics/checker.py:3159` | err( "E2016", lineno, f"incompatible initializer type for '{decl.name}'", f"Initializer type... |
| `E2017` | typecheck | `parser/semantics/checker.py:3193` | err( "E2017", assignment.location[0], f"cannot rebind outer binding '{assignment.target}'", "... |
| `E2018` | typecheck | `parser/semantics/checker.py:3206` | err( "E2018", assignment.location[0], f"assignment type mismatch for '{assignment.target}'",... |
| `E2019` | typecheck | `parser/semantics/checker.py:3216` | err( "E2019", assignment.location[0], f"cannot reassign const binding '{assignment.target}'",... |
| `E2020` | typecheck | `parser/semantics/checker.py:3251` | err( "E2020", lineno, f"duplicate declaration '{name}' in same scope", "Use a unique identifi... |
| `E2021` | typecheck | `parser/semantics/checker.py:3262` | err( "E2021", lineno, f"shadowing is forbidden for name '{name}'", "Rename the inner binding... |
| `E2022` | typecheck | `parser/semantics/checker.py:3319` | err( "E2022", lineno, f"name '{name}' is declared but not initialized", "Initialize it before... |
| `E2023` | typecheck | `parser/semantics/checker.py:3330` | err( "E2023", lineno, f"assignment to undeclared name '{name}'", "Declare it first with `var`... |
| `E2024` | typecheck | `parser/semantics/checker.py:3351` | err( "E2024", lineno, f"use of undeclared name '{name}'", "Declare it before use.", ) |
| `E2025` | typecheck | `parser/semantics/checker.py:3492` | err( "E2025", stmt.lineno, "internal binding IR shape is invalid", "Report this as an interna... |
| `E2026` | typecheck | `parser/semantics/checker.py:3502` | err("E2026", stmt.lineno, "binding kind must be a string") |
| `E2027` | typecheck | `parser/semantics/checker.py:3506` | err("E2027", stmt.lineno, "binding kind must be 'const' or 'var'") |
| `E2028` | typecheck | `parser/semantics/checker.py:3510` | err("E2028", stmt.lineno, "binding name must be a string") |
| `E2029` | typecheck | `parser/semantics/checker.py:3516` | err("E2029", stmt.lineno, "binding annotation must be a string or none") |
| `E2030` | typecheck | `parser/semantics/checker.py:3522` | err( "E2030", stmt.lineno, "binding initializer flag must be a boolean", ) |
| `E2031` | typecheck | `parser/semantics/checker.py:3562` | err( "E2031", stmt.lineno, "internal enum IR shape is invalid", "Report this as an internal p... |
| `E2032` | typecheck | `parser/semantics/checker.py:3574` | err("E2032", stmt.lineno, "enum name must be a string literal") |
| `E2033` | typecheck | `parser/semantics/checker.py:4033` | err( "E2033", lineno, f"invalid type name '{name}'", "Use PascalCase for user-defined types.", ) |
| `E2034` | typecheck | `parser/semantics/type_utils.py:11` | err("E2034", 1, "annotation is required") |
| `E2035` | typecheck | `parser/semantics/type_utils.py:26` | err( "E2035", getattr(annotation, "lineno", 1), "slice syntax is not allowed in type annotati... |
| `E2036` | typecheck | `parser/semantics/type_utils.py:45` | err( "E2036", getattr(annotation, "lineno", 1), "invalid annotation", "Use a type name like i... |
| `E2037` | typecheck | `parser/semantics/checker.py:275` | err( "E2037", stmt.lineno, "if condition must be bool", "Use a boolean expression such as `co... |
| `E2038` | typecheck | `parser/semantics/checker.py:304` | err( "E2038", stmt.lineno, "while condition must be bool", "Use a boolean expression such as... |
| `E2039` | typecheck | `parser/semantics/checker.py:1774` | err( "E2039", getattr(expr, "lineno", 1), "assignment expressions are not allowed", "Use assi... |
| `E2040` | typecheck | `parser/semantics/checker.py:1840` | err( "E2040", expr.lineno, "operator `not` requires bool operand", "Use a boolean expression... |
| `E2041` | typecheck | `parser/semantics/checker.py:1851` | err( "E2041", expr.lineno, "unary `-` requires numeric operand", "Use int or float with unary... |
| `E2042` | typecheck | `parser/semantics/checker.py:1860` | err( "E2042", expr.lineno, f"unsupported unary operator {type(expr.op).__name__}", "Only `-`... |
| `E2043` | typecheck | `parser/semantics/checker.py:1874` | err( "E2043", expr.lineno, "unsupported boolean operator", "Use `and` or `or`.", ) |
| `E2044` | typecheck | `parser/semantics/checker.py:1885` | err( "E2044", expr.lineno, "boolean operators require bool operands", "Use bool expressions w... |
| `E2045` | typecheck | `parser/semantics/checker.py:2009` | err( "E2045", getattr(expr, "lineno", 1), f"expression form {type(expr).__name__} is not supp... |
| `E2046` | typecheck | `parser/semantics/checker.py:2243` | err( "E2046", expr.lineno, "operator `+` supports numeric addition or str+str only", "Use mat... |
| `E2047` | typecheck | `parser/semantics/checker.py:2272` | err( "E2047", expr.lineno, f"unsupported arithmetic operator {type(expr.op).__name__}", "Use... |
| `E2048` | typecheck | `parser/semantics/checker.py:2283` | err( "E2048", expr.lineno, "chained comparisons are not allowed", "Split into explicit compar... |
| `E2049` | typecheck | `parser/semantics/checker.py:2298` | err( "E2049", expr.lineno, "operator is not supported", "Use ==, !=, <, <=, >, >= only.", ) |
| `E2050` | typecheck | `parser/semantics/checker.py:2308` | err( "E2050", expr.lineno, "comparison operator is not supported", "Use ==, !=, <, <=, >, >=... |
| `E2051` | typecheck | `parser/semantics/checker.py:2319` | err( "E2051", expr.lineno, "equality operands are not type-compatible", "Compare values of th... |
| `E2052` | typecheck | `parser/semantics/checker.py:2330` | err( "E2052", expr.lineno, "ordering comparisons require numeric operands", "Use int/float wi... |
| `E2053` | typecheck | `parser/semantics/checker.py:2776` | err( "E2053", expr.lineno, "slice expressions are not supported", "Use single index access li... |
| `E2054` | typecheck | `parser/semantics/checker.py:2787` | err( "E2054", expr.lineno, "index expression must be int", "Use an integer index expression.", ) |
| `E2055` | typecheck | `parser/semantics/checker.py:2798` | err( "E2055", expr.lineno, "negative indexes are not supported", "Use a non-negative index.", ) |
| `E2056` | typecheck | `parser/semantics/checker.py:2810` | err( "E2056", expr.lineno, f"cannot index non-list type '{value_type}'", "Indexing is allowed... |
| `E2057` | typecheck | `parser/semantics/checker.py:3058` | err( "E2057", lineno, f"operator `{operator}` requires numeric operands", "Use int or float o... |
| `E2058` | typecheck | `parser/semantics/checker.py:382` | err( "E2058", stmt.lineno, "nested function declarations are not allowed", "Declare functions... |
| `E2059` | typecheck | `parser/semantics/checker.py:392` | err( "E2059", stmt.lineno, f"invalid function name '{stmt.name}'", "Use snake_case for functi... |
| `E2060` | typecheck | `parser/semantics/checker.py:402` | err( "E2060", stmt.lineno, f"function '{stmt.name}' is missing return type", "Add `-> Type` i... |
| `E2061` | typecheck | `parser/semantics/checker.py:468` | err( "E2061", stmt.lineno, f"function '{stmt.name}' may exit without returning {return_type}"... |
| `E2062` | typecheck | `parser/semantics/checker.py:1092` | err( "E2062", stmt.lineno, "positional-only function parameters are not supported", "Use stan... |
| `E2063` | typecheck | `parser/semantics/checker.py:1101` | err( "E2063", stmt.lineno, "varargs/keyword-only parameters are not supported", "Use fixed pa... |
| `E2064` | typecheck | `parser/semantics/checker.py:1117` | err( "E2064", arg.lineno, f"parameter '{arg.arg}' is missing a type", "Declare every paramete... |
| `E2065` | typecheck | `parser/semantics/checker.py:1127` | err( "E2065", arg.lineno, f"duplicate parameter name '{arg.arg}'", "Use unique names for func... |
| `E2066` | typecheck | `parser/semantics/checker.py:1146` | err( "E2066", arg.lineno, f"default value type mismatch for parameter '{arg.arg}'", f"Expecte... |
| `E2067` | typecheck | `parser/semantics/checker.py:1155` | err( "E2067", arg.lineno, "required parameters must come before defaulted parameters", "Move... |
| `E2068` | typecheck | `parser/semantics/checker.py:1491` | err( "E2068", stmt.lineno, "return is only valid inside functions", "Move `return` inside a f... |
| `E2069` | typecheck | `parser/semantics/checker.py:1502` | err( "E2069", stmt.lineno, "bare return is not allowed", "Use `return none` for none-returnin... |
| `E2070` | typecheck | `parser/semantics/checker.py:1514` | err( "E2070", stmt.lineno, "none-returning function must return none", "Use `return none` or... |
| `E2071` | typecheck | `parser/semantics/checker.py:1525` | err( "E2071", stmt.lineno, f"return type mismatch: expected {expected}, got {actual}", "Retur... |
| `E2072` | typecheck | `parser/semantics/checker.py:2387` | err( "E2072", expr.lineno, "mixed positional and named arguments are not allowed", "Use eithe... |
| `E2073` | typecheck | `parser/semantics/checker.py:2574` | err( "E2073", expr.lineno, f"wrong number of arguments for '{signature.name}'", f"Expected be... |
| `E2074` | typecheck | `parser/semantics/checker.py:2587` | err( "E2074", expr.lineno, f"argument type mismatch for parameter '{params[idx].name}'", f"Ex... |
| `E2075` | typecheck | `parser/semantics/checker.py:2599` | err( "E2075", expr.lineno, f"missing required arguments for '{signature.name}'", "Provide req... |
| `E2076` | typecheck | `parser/semantics/checker.py:2614` | err( "E2076", expr.lineno, "variadic named argument expansion is not supported", "Pass explic... |
| `E2077` | typecheck | `parser/semantics/checker.py:2624` | err( "E2077", expr.lineno, f"duplicate named argument '{keyword.arg}'", "Pass each named argu... |
| `E2078` | typecheck | `parser/semantics/checker.py:2635` | err( "E2078", expr.lineno, f"unknown named argument '{keyword.arg}'", "Use only declared para... |
| `E2079` | typecheck | `parser/semantics/checker.py:2647` | err( "E2079", expr.lineno, f"argument type mismatch for parameter '{keyword.arg}'", f"Expecte... |
| `E2080` | typecheck | `parser/semantics/checker.py:2660` | err( "E2080", expr.lineno, f"missing required named arguments: {', '.join(missing)}", "Provid... |
| `E2081` | typecheck | `parser/semantics/type_utils.py:76` | err( "E2081", lineno, f"invalid function type parameter '{token_text}'", "Use `name: Type` in... |
| `E2082` | typecheck | `parser/semantics/type_utils.py:100` | err( "E2082", lineno, f"invalid function type '{type_name}'", "Use `(name: Type, ...) -> Retu... |
| `E2083` | typecheck | `parser/semantics/type_utils.py:191` | err( "E2083", lineno, f"unmatched '{opener}' in type expression", f"Ensure `{opener}` is clos... |
| `E2084` | typecheck | `parser/semantics/checker.py:292` | err( "E2084", stmt.lineno, "for loops are not supported in v1", "Use `while` loops only.", ) |
| `E2085` | typecheck | `parser/semantics/checker.py:322` | err( "E2085", stmt.lineno, "break is only valid inside while loops", "Move `break` into a `wh... |
| `E2086` | typecheck | `parser/semantics/checker.py:334` | err( "E2086", stmt.lineno, "continue is only valid inside while loops", "Move `continue` into... |
| `E2087` | typecheck | `parser/semantics/checker.py:115` | err( "E2087", getattr(stmt, "lineno", 1), "unreachable statement after control-flow terminato... |
| `E2088` | typecheck | `parser/semantics/checker.py:357` | err( "E2088", stmt.lineno, "only call expressions are allowed as standalone statements", "Use... |
| `E2089` | typecheck | `parser/semantics/checker.py:2030` | err( "E2089", expr.lineno, "ternary condition must be bool", "Use a boolean condition in `if... |
| `E2090` | typecheck | `parser/semantics/checker.py:2056` | err( "E2090", expr.lineno, "ternary branch types are not compatible", f"Use compatible branch... |
| `E2100` | typecheck | `parser/semantics/checker.py:484` | err( "E2100", stmt.lineno, "class/record declarations are only allowed at module scope", "Dec... |
| `E2101` | typecheck | `parser/semantics/checker.py:505` | err( "E2101", stmt.lineno, f"class '{stmt.name}' is missing Tython declaration marker", "Use... |
| `E2102` | typecheck | `parser/semantics/checker.py:530` | err( "E2102", getattr(member_stmt, "lineno", stmt.lineno), "records may contain only typed fi... |
| `E2103` | typecheck | `parser/semantics/checker.py:540` | err( "E2103", member.location[0], "invalid record member", "Records allow typed fields only;... |
| `E2104` | typecheck | `parser/semantics/checker.py:549` | err( "E2104", member.location[0], f"record field '{member.name}' requires a type annotation",... |
| `E2105` | typecheck | `parser/semantics/checker.py:558` | err( "E2105", member.location[0], f"duplicate record field '{member.name}'", "Use unique reco... |
| `E2106` | typecheck | `parser/semantics/checker.py:608` | err( "E2106", stmt.lineno, "a class may conform to only one record in v1", "Use a single reco... |
| `E2107` | typecheck | `parser/semantics/checker.py:640` | err( "E2107", member.location[0], f"duplicate class member '{member.name}'", "Use unique clas... |
| `E2108` | typecheck | `parser/semantics/checker.py:690` | err( "E2108", member_stmt.lineno, f"duplicate method '{signature.name}' in class '{stmt.name}... |
| `E2109` | typecheck | `parser/semantics/checker.py:701` | err( "E2109", getattr(member_stmt, "lineno", stmt.lineno), "unsupported class member", "Use i... |
| `E2110` | typecheck | `parser/semantics/checker.py:711` | err( "E2110", stmt.lineno, "class may define at most one setup block", "Keep a single `setup`... |
| `E2111` | typecheck | `parser/semantics/checker.py:746` | err( "E2111", member.location[0], "record field declarations are not allowed in classes", "Us... |
| `E2112` | typecheck | `parser/semantics/checker.py:756` | err( "E2112", member.location[0], "init fields are always public", "Remove explicit private/p... |
| `E2113` | typecheck | `parser/semantics/checker.py:766` | err( "E2113", member.location[0], f"class member '{member.name}' requires a type annotation",... |
| `E2114` | typecheck | `parser/semantics/checker.py:777` | err( "E2114", member.location[0], f"class const field '{member.name}' requires a default valu... |
| `E2115` | typecheck | `parser/semantics/checker.py:789` | err( "E2115", member.location[0], f"initializer type mismatch for class member '{member.name}... |
| `E2116` | typecheck | `parser/semantics/checker.py:811` | err( "E2116", stmt.lineno, "`setup` cannot be public", "Use bare `setup { ... }` only.", ) |
| `E2117` | typecheck | `parser/semantics/checker.py:820` | err( "E2117", stmt.lineno, "setup must return none", "Use `setup { ... }` with implicit none... |
| `E2118` | typecheck | `parser/semantics/checker.py:829` | err( "E2118", stmt.lineno, "setup must be parameterless", "Use `setup { ... }` with no parame... |
| `E2119` | typecheck | `parser/semantics/checker.py:860` | err( "E2119", stmt.lineno, f"invalid method name '{stmt.name}'", "Use snake_case for class me... |
| `E2120` | typecheck | `parser/semantics/checker.py:869` | err( "E2120", stmt.lineno, f"method '{stmt.name}' is missing return type", "Add `-> Type` to... |
| `E2121` | typecheck | `parser/semantics/checker.py:925` | err( "E2121", stmt.lineno, f"method '{stmt.name}' may exit without returning {return_type}",... |
| `E2122` | typecheck | `parser/semantics/checker.py:1012` | err( "E2122", lineno, f"class '{class_decl.name}' conforms to unknown record '{class_decl.con... |
| `E2123` | typecheck | `parser/semantics/checker.py:1028` | err( "E2123", lineno, f"private method '{field.name}' cannot satisfy public record requiremen... |
| `E2124` | typecheck | `parser/semantics/checker.py:1039` | err( "E2124", lineno, f"method '{field.name}' does not match required record function type",... |
| `E2125` | typecheck | `parser/semantics/checker.py:1049` | err( "E2125", lineno, f"class '{class_decl.name}' is missing public member '{field.name}' req... |
| `E2126` | typecheck | `parser/semantics/checker.py:1058` | err( "E2126", lineno, f"member '{field.name}' type mismatch for record conformance", f"Expect... |
| `E2127` | typecheck | `parser/semantics/checker.py:1069` | err( "E2127", lineno, f"class '{class_decl.name}' is missing public field '{field.name}' requ... |
| `E2128` | typecheck | `parser/semantics/checker.py:1078` | err( "E2128", lineno, f"field '{field.name}' type mismatch for record conformance", f"Expecte... |
| `E2129` | typecheck | `parser/semantics/checker.py:1190` | err( "E2129", stmt.lineno, "unsupported method parameter form", "Use fixed named method param... |
| `E2130` | typecheck | `parser/semantics/checker.py:1200` | err( "E2130", stmt.lineno, "methods must declare implicit receiver as `this`", "Declare metho... |
| `E2131` | typecheck | `parser/semantics/checker.py:1209` | err( "E2131", stmt.lineno, "method receiver must not be annotated", "Do not annotate the impl... |
| `E2132` | typecheck | `parser/semantics/checker.py:1226` | err( "E2132", arg.lineno, f"parameter '{arg.arg}' is missing a type", "Declare every method p... |
| `E2133` | typecheck | `parser/semantics/checker.py:1235` | err( "E2133", arg.lineno, f"duplicate parameter name '{arg.arg}'", "Use unique method paramet... |
| `E2134` | typecheck | `parser/semantics/checker.py:1253` | err( "E2134", arg.lineno, f"default value type mismatch for parameter '{arg.arg}'", f"Expecte... |
| `E2135` | typecheck | `parser/semantics/checker.py:1262` | err( "E2135", arg.lineno, "required parameters must come before defaulted parameters", "Move... |
| `E2136` | typecheck | `parser/semantics/checker.py:1311` | err( "E2136", getattr(stmt, "lineno", 1), "unsupported function decorator", "Only internal `p... |
| `E2137` | typecheck | `parser/semantics/checker.py:1384` | err("E2137", stmt.lineno, "invalid record marker") |
| `E2138` | typecheck | `parser/semantics/checker.py:1388` | err("E2138", stmt.lineno, "invalid record visibility marker") |
| `E2139` | typecheck | `parser/semantics/checker.py:1402` | err("E2139", stmt.lineno, "invalid class marker") |
| `E2140` | typecheck | `parser/semantics/checker.py:1408` | err("E2140", stmt.lineno, "invalid class conformance marker") |
| `E2141` | typecheck | `parser/semantics/checker.py:1414` | err("E2141", stmt.lineno, "invalid class visibility marker") |
| `E2142` | typecheck | `parser/semantics/checker.py:1432` | err( "E2142", getattr(stmt, "lineno", 1), "internal class member IR shape is invalid", "Repor... |
| `E2143` | typecheck | `parser/semantics/checker.py:1442` | err("E2143", stmt.lineno, "class member kind must be string") |
| `E2144` | typecheck | `parser/semantics/checker.py:1446` | err("E2144", stmt.lineno, "class member name must be string") |
| `E2145` | typecheck | `parser/semantics/checker.py:1452` | err("E2145", stmt.lineno, "class member type must be string/none") |
| `E2146` | typecheck | `parser/semantics/checker.py:1458` | err("E2146", stmt.lineno, "class member initializer flag must be bool") |
| `E2147` | typecheck | `parser/semantics/checker.py:1464` | err("E2147", stmt.lineno, "class member public flag must be bool") |
| `E2148` | typecheck | `parser/semantics/checker.py:1470` | err( "E2148", stmt.lineno, "class member class-context flag must be bool" ) |
| `E2149` | typecheck | `parser/semantics/checker.py:1476` | err("E2149", stmt.lineno, "class member declaration used outside class") |
| `E2150` | typecheck | `parser/semantics/checker.py:3984` | err( "E2150", expr.lineno, f"Matrix has no method '{method_name}'", "Use Matrix methods only.... |
| `E2151` | typecheck | `parser/semantics/checker.py:2377` | err( "E2151", expr.lineno, "setup cannot be called manually", "setup runs automatically durin... |
| `E2152` | typecheck | `parser/semantics/checker.py:3532` | err( "E2152", stmt.lineno, "binding visibility flag must be a boolean", ) |
| `E2153` | typecheck | `parser/semantics/checker.py:2830` | err( "E2153", getattr(expr, "lineno", 1), "internal record literal IR shape is invalid", "Rep... |
| `E2154` | typecheck | `parser/semantics/checker.py:2842` | err("E2154", expr.lineno, "record literal type must be a string") |
| `E2155` | typecheck | `parser/semantics/checker.py:2846` | err("E2155", expr.lineno, "record literal fields must be a list") |
| `E2156` | typecheck | `parser/semantics/checker.py:2852` | err( "E2156", expr.lineno, f"unknown record type '{type_node.value}'", "Declare the record be... |
| `E2157` | typecheck | `parser/semantics/checker.py:2871` | err("E2157", expr.lineno, "invalid record field entry") |
| `E2158` | typecheck | `parser/semantics/checker.py:2878` | err("E2158", expr.lineno, "record field name must be string") |
| `E2159` | typecheck | `parser/semantics/checker.py:2883` | err( "E2159", expr.lineno, f"duplicate record field '{field_name}'", "Provide each field at m... |
| `E2160` | typecheck | `parser/semantics/checker.py:2897` | err( "E2160", expr.lineno, f"unknown record field '{field_name}' for '{record_decl.name}'", "... |
| `E2161` | typecheck | `parser/semantics/checker.py:2907` | err( "E2161", expr.lineno, f"missing required record field '{field.name}'", "Provide all requ... |
| `E2162` | typecheck | `parser/semantics/checker.py:2917` | err( "E2162", expr.lineno, f"record field type mismatch for '{field.name}'", f"Expected {fiel... |
| `E2163` | typecheck | `parser/semantics/checker.py:2931` | err( "E2163", expr.lineno, f"class constructor '{class_decl.name}' requires named arguments",... |
| `E2164` | typecheck | `parser/semantics/checker.py:2947` | err( "E2164", expr.lineno, "variadic named argument expansion is not supported", "Pass explic... |
| `E2165` | typecheck | `parser/semantics/checker.py:2956` | err( "E2165", expr.lineno, f"duplicate constructor argument '{keyword.arg}'", "Pass each cons... |
| `E2166` | typecheck | `parser/semantics/checker.py:2967` | err( "E2166", expr.lineno, f"unknown constructor argument '{keyword.arg}' for '{class_decl.na... |
| `E2167` | typecheck | `parser/semantics/checker.py:2978` | err( "E2167", expr.lineno, f"constructor argument type mismatch for '{keyword.arg}'", f"Expec... |
| `E2168` | typecheck | `parser/semantics/checker.py:2991` | err( "E2168", expr.lineno, f"missing required constructor arguments: {', '.join(missing)}", "... |
| `E2169` | typecheck | `parser/semantics/checker.py:3013` | err("E2169", lineno, "instance assignment outside class context") |
| `E2170` | typecheck | `parser/semantics/checker.py:3018` | err( "E2170", lineno, f"unknown instance field '{attr}'", "Assign only to declared class fiel... |
| `E2171` | typecheck | `parser/semantics/checker.py:3027` | err( "E2171", lineno, f"cannot assign immutable field '{attr}'", "Assign only to `init var`/`... |
| `E2172` | typecheck | `parser/semantics/checker.py:3038` | err( "E2172", lineno, f"assignment type mismatch for field '{attr}'", f"Expected {member.type... |
| `E2173` | typecheck | `parser/semantics/checker.py:1548` | err( "E2173", handler.lineno, "typed catch cannot appear after catch-all", "Move catch-all ha... |
| `E2174` | typecheck | `parser/semantics/checker.py:1584` | err( "E2174", handler.lineno, "catch-all handler must be last", "Move catch-all handler to th... |
| `E2175` | typecheck | `parser/semantics/checker.py:1595` | err( "E2175", handler.lineno, "catch type must be a named error record", "Use `catch err: Err... |
| `E2176` | typecheck | `parser/semantics/checker.py:1617` | err( "E2176", handler.lineno, f"catch type '{catch_type.id}' is not a declared record", "Decl... |
| `E2177` | typecheck | `parser/semantics/checker.py:1642` | err( "E2177", stmt.lineno, "raise requires an error value", "Use `raise ErrorType { ... }`.", ) |
| `E2178` | typecheck | `parser/semantics/checker.py:1652` | err( "E2178", stmt.lineno, "`raise ... from ...` is not supported", "Raise recoverable errors... |
| `E2179` | typecheck | `parser/semantics/checker.py:1663` | err( "E2179", stmt.lineno, "raised value must be a declared error record", "Raise values of r... |
| `E2180` | typecheck | `parser/semantics/checker.py:1678` | err( "E2180", stmt.lineno, f"raise of '{error_type}' is not allowed at module scope", "Handle... |
| `E2181` | typecheck | `parser/semantics/checker.py:1686` | err( "E2181", stmt.lineno, f"raised error '{error_type}' is not declared in throws clause", "... |
| `E2182` | typecheck | `parser/semantics/checker.py:417` | err( "E2182", stmt.lineno, f"throws type '{thrown_type}' is not a declared record", "Declare... |
| `E2183` | typecheck | `parser/semantics/checker.py:802` | err( "E2183", stmt.lineno, "setup cannot declare throws", "Handle setup errors inside setup o... |
| `E2184` | typecheck | `parser/semantics/checker.py:1331` | err( "E2184", stmt.lineno, "throws decorator metadata must use positional type names", "Use i... |
| `E2185` | typecheck | `parser/semantics/checker.py:1350` | err( "E2185", stmt.lineno, f"duplicate throws type '{arg.value}'", "List each throws type onc... |
| `E2186` | typecheck | `parser/semantics/checker.py:2359` | err( "E2186", expr.lineno, "panic expects exactly one argument", 'Use `panic("message")`.', ) |
| `E2187` | typecheck | `parser/semantics/checker.py:2512` | err( "E2187", expr.lineno, "try propagation requires exactly one call argument", "Use `try fn... |
| `E2188` | typecheck | `parser/semantics/checker.py:2521` | err( "E2188", expr.lineno, "try propagation is only valid inside callable scope", "Use `try`... |
| `E2189` | typecheck | `parser/semantics/checker.py:2532` | err( "E2189", expr.lineno, "try propagation target must be a call expression", "Use `try fn(.... |
| `E2190` | typecheck | `parser/semantics/checker.py:2545` | err( "E2190", expr.lineno, "try propagation requires a throwing call", "Use plain call for no... |
| `E2191` | typecheck | `parser/semantics/checker.py:2557` | err( "E2191", expr.lineno, f"try propagation uses undeclared throws type(s): {missing}", "Add... |
| `E2192` | typecheck | `parser/semantics/checker.py:2429` | err( "E2192", expr.lineno, f"call to throwing method '{expr.func.attr}' must be handled", "Wr... |
| `E2200` | typecheck | `parser/semantics/checker.py:131` | err( "E2200", stmt.lineno, "native import must use slash-separated module path", "Use `import... |
| `E2201` | typecheck | `parser/semantics/checker.py:3403` | err( "E2201", stmt.lineno, "internal native import IR shape is invalid", "Report this as an i... |
| `E2202` | typecheck | `parser/semantics/checker.py:3415` | err("E2202", stmt.lineno, "native import target must be string") |
| `E2203` | typecheck | `parser/semantics/checker.py:3421` | err("E2203", stmt.lineno, "native import alias must be string/none") |
| `E2204` | typecheck | `parser/semantics/checker.py:3430` | err( "E2204", stmt.lineno, "internal file import IR shape is invalid", "Report this as an int... |
| `E2205` | typecheck | `parser/semantics/checker.py:3442` | err("E2205", stmt.lineno, "file import path must be string") |
| `E2206` | typecheck | `parser/semantics/checker.py:3448` | err("E2206", stmt.lineno, "file import alias must be string") |
| `E2207` | typecheck | `parser/semantics/checker.py:3457` | err( "E2207", stmt.lineno, "internal pyimport IR shape is invalid", "Report this as an intern... |
| `E2208` | typecheck | `parser/semantics/checker.py:3469` | err("E2208", stmt.lineno, "pyimport module must be string") |
| `E2209` | typecheck | `parser/semantics/checker.py:3475` | err("E2209", stmt.lineno, "pyimport alias must be string/none") |
| `E2210` | typecheck | `parser/semantics/checker.py:146` | err( "E2210", stmt.lineno, "file import path must be relative", "Use `./` or `../` path prefi... |
| `E2211` | typecheck | `parser/semantics/checker.py:161` | err( "E2211", stmt.lineno, f"invalid pyimport module '{module_name}'", "Use dotted Python mod... |
| `E3000` | project | `parser/project.py:68` | _diag( "E3000", 1, "project.toml not found", "Run command from project root (or subdirectory... |
| `E3001` | project | `parser/project.py:81` | _diag( "E3001", 1, "project.toml missing", "Create project.toml in project root.", ) |
| `E3002` | project | `parser/project.py:93` | _diag("E3002", 1, "[project] section missing", "Add [project] section.") |
| `E3004` | project | `parser/project.py:99` | _diag( "E3004", 1, f"invalid project name '{name}'", "Use snake_case identifier style.", ) |
| `E3009` | project | `parser/project.py:115` | _diag( "E3009", 1, "[packages] must be table", "Use [packages.<name>] sections.", ) |
| `E3010` | project | `parser/project.py:126` | _diag( "E3010", 1, f"invalid package name '{name_key}'", "Use snake_case identifier names.", ) |
| `E3011` | project | `parser/project.py:135` | _diag( "E3011", 1, f"package '{name_key}' must be table", "Use [packages.<name>] table.", ) |
| `E3013` | project | `parser/project.py:146` | _diag( "E3013", 1, f"package '{name_key}' must define `rev`", "Use `rev` with exact git commi... |
| `E3015` | project | `parser/project.py:162` | _diag( "E3015", 1, "[python] must be table", "Use [python].dependencies list." ) |
| `E3016` | project | `parser/project.py:171` | _diag( "E3016", 1, "[python].dependencies must be string list", "Use dependency strings.", ) |
| `E3020` | project | `parser/project.py:198` | _diag("E3020", 1, "invalid project.lock [packages]", "Regenerate lockfile.") |
| `E3021` | project | `parser/project.py:205` | _diag( "E3021", 1, f"invalid lock package '{name}'", "Regenerate lockfile." ) |
| `E3026` | project | `parser/project.py:226` | _diag("E3026", 1, "invalid project.lock [python]", "Regenerate lockfile.") |
| `E3027` | project | `parser/project.py:231` | _diag( "E3027", 1, "invalid lock python dependencies", "Regenerate lockfile." ) |
| `E3030` | project | `parser/project.py:300` | _diag( "E3030", 1, f"failed to clone package '{locked.name}'", completed.stderr.strip() or "c... |
| `E3031` | project | `parser/project.py:316` | _diag( "E3031", 1, f"failed to checkout commit '{locked.commit}' for package '{locked.name}'"... |
| `E3032` | project | `parser/project.py:371` | _diag( "E3032", 1, f"invalid rev '{requested}'", "Use exact 40-char git commit SHA in [packag... |
| `E3201` | build | `parser/project_build.py:196` | SyntaxError( f"[E3201] Line 1: unresolved native import '{raw}'. Hint: define matching local... |
| `E3202` | build | `parser/project_build.py:72` | SyntaxError( f"[E3202] Line 1: unresolved file import '{raw}'. Hint: ensure imported .ty file... |
| `E3203` | build | `parser/project_build.py:102` | SyntaxError( f"[E3203] Line 1: target '{target_file}' not in build output. Hint: check file p... |
| `E3204` | build | `parser/project_build.py:134` | SyntaxError( "[E3204] Line 1: src/ directory missing. Hint: create src/ with .ty sources." ) |
| `E3205` | build | `parser/project_build.py:203` | SyntaxError( f"[E3205] Line 1: invalid file import '{raw}'. Hint: file imports must start wit... |
| `E9001` | diagnostics | `parser/diagnostics.py:269` | make_diagnostic( code="E9001", severity="error", phase=default_phase, message=text or "syntax... |

## Runtime errors

| Code | Area | Source | Summary |
| --- | --- | --- | --- |
| `R0001` | diagnostics | `parser/diagnostics.py:281` | code = "P0001" if is_panic else "R0001" |

## Panic and internal errors

| Code | Area | Source | Summary |
| --- | --- | --- | --- |
| `P0001` | diagnostics | `parser/diagnostics.py:281` | code = "P0001" if is_panic else "R0001" |
