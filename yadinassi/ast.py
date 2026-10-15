"""Syntax tree independent of execution and host objects."""

from dataclasses import dataclass

from .lexer import Token


@dataclass
class Node:
    token: Token


@dataclass
class Literal(Node):
    value: object


@dataclass
class OmittedArgument(Node):
    pass


@dataclass
class Name(Node):
    name: str


@dataclass
class Group(Node):
    expression: Node


@dataclass
class Unary(Node):
    operator: str
    operand: Node


@dataclass
class Binary(Node):
    left: Node
    operator: str
    right: Node


@dataclass
class Conditional(Node):
    condition: Node
    when_true: Node
    when_false: Node


@dataclass
class Attribute(Node):
    object: Node
    name: str


@dataclass
class Index(Node):
    object: Node
    index: Node


@dataclass
class Call(Node):
    callee: Node
    arguments: list[Node]


@dataclass
class New(Node):
    name: str
    arguments: list[Node]


@dataclass
class Assign(Node):
    target: Node
    value: Node


@dataclass
class ExpressionStatement(Node):
    expression: Node


@dataclass
class If(Node):
    branches: list[tuple[Node, list[Node]]]
    otherwise: list[Node]


@dataclass
class For(Node):
    name: str
    start: Node
    end: Node
    body: list[Node]


@dataclass
class ForEach(Node):
    name: str
    collection: Node
    body: list[Node]


@dataclass
class While(Node):
    condition: Node
    body: list[Node]


@dataclass
class Break(Node):
    pass


@dataclass
class Continue(Node):
    pass


@dataclass
class Var(Node):
    names: list[str]


@dataclass
class Parameter(Node):
    name: str
    by_value: bool
    default: Node | None = None


@dataclass
class Routine(Node):
    name: str
    parameters: list[Parameter]
    is_function: bool
    exported: bool
    body: list[Node]


@dataclass
class Return(Node):
    value: Node | None
