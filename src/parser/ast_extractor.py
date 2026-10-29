"""Tree-sitter AST Symbol & Dependency Edge Extractor."""

from __future__ import annotations

import ast

import tree_sitter
import tree_sitter_language_pack as tslp

from src.core.logger import setup_logger
from src.parser.models import CodeEdge, CodeSymbol, EdgeType, SymbolKind

logger = setup_logger("agentic-ast-extractor")

LANGUAGE_PARSER_MAP: dict[str, str] = {
    "python": "python",
    "javascript": "javascript",
    "typescript": "typescript",
    "go": "go",
    "rust": "rust",
    "java": "java",
    "cpp": "cpp",
    "c": "c",
    "csharp": "csharp",
}


class ASTSymbolExtractor:
    """Extracts structured symbols, method signatures, docstrings, and import edges using Tree-sitter."""

    def __init__(self) -> None:
        self._languages: dict[str, tree_sitter.Language] = {}
        self._current_source_bytes: bytes = b""

    def _get_parser(self, language: str) -> tree_sitter.Parser | None:
        """Retrieves or lazily loads a Tree-sitter parser for a language."""
        target_lang = LANGUAGE_PARSER_MAP.get(language.lower())
        if not target_lang:
            return None

        if target_lang not in self._languages:
            try:
                self._languages[target_lang] = tslp.get_language(target_lang)
            except Exception as e:
                logger.debug(f"Could not initialize language grammar for {language}: {e}")
                return None

        try:
            return tree_sitter.Parser(self._languages[target_lang])
        except Exception as e:
            logger.debug(f"Could not instantiate parser for {language}: {e}")
            return None

    def extract(
        self, file_path: str, content: str, language: str
    ) -> tuple[list[CodeSymbol], list[CodeEdge]]:
        """Parses source code into structured symbols and dependency edges."""
        if not content.strip():
            return [], []

        symbols: list[CodeSymbol] = []
        edges: list[CodeEdge] = []
        lines = content.splitlines()
        norm_path = file_path.replace("\\", "/")

        if language == "python":
            self._extract_python_stdlib(content, lines, norm_path, symbols, edges)
            return symbols, edges

        parser = self._get_parser(language)
        if not parser:
            return [], []

        source_bytes = content.encode("utf-8")
        self._current_source_bytes = source_bytes
        try:
            tree = parser.parse(source_bytes)
        except Exception as e:
            logger.warning(f"AST parsing failed for {file_path}: {e}")
            return [], []

        if language in ("typescript", "javascript"):
            self._extract_typescript(tree.root_node, lines, norm_path, language, symbols, edges)
        elif language == "go":
            self._extract_go(tree.root_node, lines, norm_path, symbols, edges)
        else:
            self._extract_generic(tree.root_node, lines, norm_path, language, symbols, edges)

        return symbols, edges

    def _extract_python_stdlib(
        self,
        content: str,
        lines: list[str],
        file_path: str,
        symbols: list[CodeSymbol],
        edges: list[CodeEdge],
    ) -> None:
        """Extracts Python symbols, methods, and imports using Python's native AST parser."""
        try:
            tree = ast.parse(content)
        except Exception as e:
            logger.debug(f"ast.parse failed for {file_path}: {e}")
            return

        for node in tree.body:
            # 1. Imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    edges.append(
                        CodeEdge(
                            source_symbol=file_path,
                            target_symbol=alias.name,
                            edge_type=EdgeType.IMPORTS,
                            source_file=file_path,
                            target_file=alias.name.replace(".", "/") + ".py",
                        )
                    )
            elif isinstance(node, ast.ImportFrom):
                module_name = node.module or ""
                edges.append(
                    CodeEdge(
                        source_symbol=file_path,
                        target_symbol=module_name,
                        edge_type=EdgeType.IMPORTS,
                        source_file=file_path,
                        target_file=module_name.replace(".", "/") + ".py",
                    )
                )

            # 2. Classes
            elif isinstance(node, ast.ClassDef):
                start_l = node.lineno
                end_l = getattr(node, "end_lineno", node.lineno)
                sig = (
                    lines[start_l - 1].strip()
                    if 0 < start_l <= len(lines)
                    else f"class {node.name}"
                )
                doc = ast.get_docstring(node)
                symbols.append(
                    CodeSymbol(
                        name=node.name,
                        qualified_name=node.name,
                        kind=SymbolKind.CLASS,
                        file_path=file_path,
                        start_line=start_l,
                        end_line=end_l,
                        signature=sig,
                        docstring=doc,
                        language="python",
                    )
                )

                # Class methods
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        m_start = item.lineno
                        m_end = getattr(item, "end_lineno", item.lineno)
                        m_sig = (
                            lines[m_start - 1].strip()
                            if 0 < m_start <= len(lines)
                            else f"def {item.name}"
                        )
                        m_doc = ast.get_docstring(item)
                        symbols.append(
                            CodeSymbol(
                                name=item.name,
                                qualified_name=f"{node.name}.{item.name}",
                                kind=SymbolKind.METHOD,
                                file_path=file_path,
                                start_line=m_start,
                                end_line=m_end,
                                signature=m_sig,
                                docstring=m_doc,
                                language="python",
                            )
                        )

            # 3. Top-level functions
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start_l = node.lineno
                end_l = getattr(node, "end_lineno", node.lineno)
                sig = (
                    lines[start_l - 1].strip() if 0 < start_l <= len(lines) else f"def {node.name}"
                )
                doc = ast.get_docstring(node)
                symbols.append(
                    CodeSymbol(
                        name=node.name,
                        qualified_name=node.name,
                        kind=SymbolKind.FUNCTION,
                        file_path=file_path,
                        start_line=start_l,
                        end_line=end_l,
                        signature=sig,
                        docstring=doc,
                        language="python",
                    )
                )

    def _extract_python(
        self,
        root_node: tree_sitter.Node,
        lines: list[str],
        file_path: str,
        symbols: list[CodeSymbol],
        edges: list[CodeEdge],
    ) -> None:
        for node in root_node.children:
            # 1. Imports
            if node.type in ("import_statement", "import_from_statement"):
                self._extract_python_import(node, file_path, edges)

            # 2. Top-level classes
            elif node.type == "class_definition":
                class_name = self._node_text(self._child(node, "name"))
                if not class_name:
                    continue
                start_l, end_l = node.start_point.row + 1, node.end_point.row + 1
                sig = (
                    lines[node.start_point.row].strip()
                    if node.start_point.row < len(lines)
                    else f"class {class_name}"
                )
                doc = self._extract_python_docstring(self._child(node, "body"))

                symbols.append(
                    CodeSymbol(
                        name=class_name,
                        qualified_name=class_name,
                        kind=SymbolKind.CLASS,
                        file_path=file_path,
                        start_line=start_l,
                        end_line=end_l,
                        signature=sig,
                        docstring=doc,
                        language="python",
                    )
                )

                # Extract class methods
                body_node = self._child(node, "body")
                if body_node:
                    for child in body_node.children:
                        target_func = child
                        if child.type == "decorated_definition":
                            for inner in child.children:
                                if inner.type in (
                                    "function_definition",
                                    "async_function_definition",
                                ):
                                    target_func = inner
                                    break

                        if target_func.type in ("function_definition", "async_function_definition"):
                            method_name = self._node_text(self._child(target_func, "name"))
                            if method_name:
                                m_start, m_end = (
                                    target_func.start_point.row + 1,
                                    target_func.end_point.row + 1,
                                )
                                m_sig = (
                                    lines[target_func.start_point.row].strip()
                                    if target_func.start_point.row < len(lines)
                                    else f"def {method_name}"
                                )
                                m_doc = self._extract_python_docstring(
                                    self._child(target_func, "body")
                                )
                                symbols.append(
                                    CodeSymbol(
                                        name=method_name,
                                        qualified_name=f"{class_name}.{method_name}",
                                        kind=SymbolKind.METHOD,
                                        file_path=file_path,
                                        start_line=m_start,
                                        end_line=m_end,
                                        signature=m_sig,
                                        docstring=m_doc,
                                        language="python",
                                    )
                                )

            # 3. Top-level functions
            elif node.type in ("function_definition", "async_function_definition"):
                func_name = self._node_text(self._child(node, "name"))
                if not func_name:
                    continue
                start_l, end_l = node.start_point.row + 1, node.end_point.row + 1
                sig = (
                    lines[node.start_point.row].strip()
                    if node.start_point.row < len(lines)
                    else f"def {func_name}"
                )
                doc = self._extract_python_docstring(self._child(node, "body"))
                symbols.append(
                    CodeSymbol(
                        name=func_name,
                        qualified_name=func_name,
                        kind=SymbolKind.FUNCTION,
                        file_path=file_path,
                        start_line=start_l,
                        end_line=end_l,
                        signature=sig,
                        docstring=doc,
                        language="python",
                    )
                )

    def _extract_typescript(
        self,
        root_node: tree_sitter.Node,
        lines: list[str],
        file_path: str,
        language: str,
        symbols: list[CodeSymbol],
        edges: list[CodeEdge],
    ) -> None:
        # Collect top-level nodes, unwrapping export statements
        raw_nodes: list[tree_sitter.Node] = []
        for child in root_node.children:
            if child.type == "export_statement":
                for sub in child.children:
                    if sub.type in (
                        "interface_declaration",
                        "class_declaration",
                        "function_declaration",
                        "type_alias_declaration",
                    ):
                        raw_nodes.append(sub)
            else:
                raw_nodes.append(child)

        for node in raw_nodes:
            # 1. Imports
            if node.type == "import_statement":
                source_node = self._child(node, "source")
                if source_node:
                    import_target = self._node_text(source_node).strip("'\"")
                    edges.append(
                        CodeEdge(
                            source_symbol=file_path,
                            target_symbol=import_target,
                            edge_type=EdgeType.IMPORTS,
                            source_file=file_path,
                            target_file=import_target,
                        )
                    )

            # 2. Classes
            elif node.type == "class_declaration":
                class_name = self._node_text(self._child(node, "name"))
                if class_name:
                    start_l, end_l = node.start_point.row + 1, node.end_point.row + 1
                    sig = (
                        lines[node.start_point.row].strip()
                        if node.start_point.row < len(lines)
                        else f"class {class_name}"
                    )
                    symbols.append(
                        CodeSymbol(
                            name=class_name,
                            qualified_name=class_name,
                            kind=SymbolKind.CLASS,
                            file_path=file_path,
                            start_line=start_l,
                            end_line=end_l,
                            signature=sig,
                            docstring=None,
                            language=language,
                        )
                    )

            # 3. Functions
            elif node.type == "function_declaration":
                func_name = self._node_text(self._child(node, "name"))
                if func_name:
                    start_l, end_l = node.start_point.row + 1, node.end_point.row + 1
                    sig = (
                        lines[node.start_point.row].strip()
                        if node.start_point.row < len(lines)
                        else f"function {func_name}"
                    )
                    symbols.append(
                        CodeSymbol(
                            name=func_name,
                            qualified_name=func_name,
                            kind=SymbolKind.FUNCTION,
                            file_path=file_path,
                            start_line=start_l,
                            end_line=end_l,
                            signature=sig,
                            docstring=None,
                            language=language,
                        )
                    )

            # 4. Interfaces & Type Aliases
            elif node.type in ("interface_declaration", "type_alias_declaration"):
                type_name = self._node_text(self._child(node, "name"))
                if type_name:
                    kind = (
                        SymbolKind.INTERFACE
                        if node.type == "interface_declaration"
                        else SymbolKind.TYPE_ALIAS
                    )
                    start_l, end_l = node.start_point.row + 1, node.end_point.row + 1
                    sig = (
                        lines[node.start_point.row].strip()
                        if node.start_point.row < len(lines)
                        else type_name
                    )
                    symbols.append(
                        CodeSymbol(
                            name=type_name,
                            qualified_name=type_name,
                            kind=kind,
                            file_path=file_path,
                            start_line=start_l,
                            end_line=end_l,
                            signature=sig,
                            docstring=None,
                            language=language,
                        )
                    )

    def _extract_go(
        self,
        root_node: tree_sitter.Node,
        lines: list[str],
        file_path: str,
        symbols: list[CodeSymbol],
        edges: list[CodeEdge],
    ) -> None:
        for node in root_node.children:
            if node.type == "function_declaration":
                name = self._node_text(self._child(node, "name"))
                if name:
                    start_l, end_l = node.start_point.row + 1, node.end_point.row + 1
                    sig = (
                        lines[node.start_point.row].strip()
                        if node.start_point.row < len(lines)
                        else f"func {name}"
                    )
                    symbols.append(
                        CodeSymbol(
                            name=name,
                            qualified_name=name,
                            kind=SymbolKind.FUNCTION,
                            file_path=file_path,
                            start_line=start_l,
                            end_line=end_l,
                            signature=sig,
                            language="go",
                        )
                    )
            elif node.type == "method_declaration":
                name = self._node_text(self._child(node, "name"))
                if name:
                    start_l, end_l = node.start_point.row + 1, node.end_point.row + 1
                    sig = (
                        lines[node.start_point.row].strip()
                        if node.start_point.row < len(lines)
                        else f"func {name}"
                    )
                    symbols.append(
                        CodeSymbol(
                            name=name,
                            qualified_name=name,
                            kind=SymbolKind.METHOD,
                            file_path=file_path,
                            start_line=start_l,
                            end_line=end_l,
                            signature=sig,
                            language="go",
                        )
                    )

    def _extract_generic(
        self,
        root_node: tree_sitter.Node,
        lines: list[str],
        file_path: str,
        language: str,
        symbols: list[CodeSymbol],
        edges: list[CodeEdge],
    ) -> None:
        """Fallback generic symbol extractor for C, C++, Rust, Java, C#."""
        for node in root_node.children:
            if (
                "function" in node.type
                or "method" in node.type
                or "class" in node.type
                or "struct" in node.type
            ):
                name_node = self._child(node, "name")
                name = self._node_text(name_node) if name_node else None
                if name:
                    kind = (
                        SymbolKind.CLASS
                        if "class" in node.type or "struct" in node.type
                        else SymbolKind.FUNCTION
                    )
                    start_l, end_l = node.start_point.row + 1, node.end_point.row + 1
                    sig = (
                        lines[node.start_point.row].strip()
                        if node.start_point.row < len(lines)
                        else name
                    )
                    symbols.append(
                        CodeSymbol(
                            name=name,
                            qualified_name=name,
                            kind=kind,
                            file_path=file_path,
                            start_line=start_l,
                            end_line=end_l,
                            signature=sig,
                            language=language,
                        )
                    )

    def _extract_python_import(
        self, node: tree_sitter.Node, file_path: str, edges: list[CodeEdge]
    ) -> None:
        if node.type == "import_statement":
            for child in node.children:
                if child.type == "dotted_name":
                    target = self._node_text(child)
                    edges.append(
                        CodeEdge(
                            source_symbol=file_path,
                            target_symbol=target,
                            edge_type=EdgeType.IMPORTS,
                            source_file=file_path,
                            target_file=target.replace(".", "/") + ".py",
                        )
                    )
        elif node.type == "import_from_statement":
            module_name = self._node_text(self._child(node, "module_name")) or ""
            edges.append(
                CodeEdge(
                    source_symbol=file_path,
                    target_symbol=module_name,
                    edge_type=EdgeType.IMPORTS,
                    source_file=file_path,
                    target_file=module_name.replace(".", "/") + ".py",
                )
            )

    def _extract_python_docstring(self, body_node: tree_sitter.Node | None) -> str | None:
        if not body_node:
            return None
        strip_chars = chr(34) + chr(39) + " \n\r"
        for child in body_node.children:
            if child.type == "string":
                return self._node_text(child).strip(strip_chars)
            elif child.type == "expression_statement":
                for subchild in child.children:
                    if subchild.type == "string":
                        return self._node_text(subchild).strip(strip_chars)
            elif child.type not in ("comment", "\n"):
                break
        return None

    def _child(self, node: tree_sitter.Node | None, field_name: str) -> tree_sitter.Node | None:
        """Safely fetches a child by field name using children_by_field_name to avoid C ABI heap corruption."""
        if not node:
            return None
        try:
            children = node.children_by_field_name(field_name)
            return children[0] if children else None
        except Exception:
            return None

    def _node_text(self, node: tree_sitter.Node | None) -> str:
        if not node:
            return ""
        try:
            return (
                self._current_source_bytes[node.start_byte : node.end_byte]
                .decode("utf-8", errors="ignore")
                .strip()
            )
        except Exception:
            return ""
