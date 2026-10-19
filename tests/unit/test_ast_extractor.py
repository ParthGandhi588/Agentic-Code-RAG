"""Unit tests for Tree-sitter AST symbol and edge extraction."""

from src.parser.ast_extractor import ASTSymbolExtractor
from src.parser.models import EdgeType, SymbolKind


def test_python_ast_extraction() -> None:
    code = '''
import os
from datetime import datetime

class PaymentGateway:
    """Handles third-party credit card processing."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def charge(self, amount: float, currency: str = "USD") -> bool:
        """Executes a card charge."""
        return True

def calculate_tax(subtotal: float) -> float:
    """Calculates sales tax."""
    return subtotal * 0.08
'''
    extractor = ASTSymbolExtractor()
    symbols, edges = extractor.extract("src/billing/gateway.py", code, "python")

    # 1. Verify Symbols
    names = {s.name: s for s in symbols}
    assert "PaymentGateway" in names
    assert names["PaymentGateway"].kind == SymbolKind.CLASS
    assert "Handles third-party credit card processing" in (names["PaymentGateway"].docstring or "")
    assert names["PaymentGateway"].start_line == 5

    assert "charge" in names
    assert names["charge"].kind == SymbolKind.METHOD
    assert names["charge"].qualified_name == "PaymentGateway.charge"
    assert "Executes a card charge" in (names["charge"].docstring or "")

    assert "calculate_tax" in names
    assert names["calculate_tax"].kind == SymbolKind.FUNCTION

    # 2. Verify Import Edges
    assert any(e.edge_type == EdgeType.IMPORTS and "os" in e.target_symbol for e in edges)
    assert any(e.edge_type == EdgeType.IMPORTS and "datetime" in e.target_symbol for e in edges)


def test_typescript_ast_extraction() -> None:
    ts_code = """
import { OrderModel } from "./models";

export interface BillingConfig {
    apiKey: string;
    timeoutMs: number;
}

export class OrderService {
    processOrder(orderId: string): boolean {
        return true;
    }
}

export function formatCurrency(amount: number): string {
    return "$" + amount.toFixed(2);
}
"""
    extractor = ASTSymbolExtractor()
    symbols, edges = extractor.extract("src/services/order.ts", ts_code, "typescript")

    names = {s.name: s for s in symbols}
    assert "BillingConfig" in names
    assert names["BillingConfig"].kind == SymbolKind.INTERFACE

    assert "OrderService" in names
    assert names["OrderService"].kind == SymbolKind.CLASS

    assert "formatCurrency" in names
    assert names["formatCurrency"].kind == SymbolKind.FUNCTION

    assert any(e.edge_type == EdgeType.IMPORTS and "./models" in e.target_symbol for e in edges)
