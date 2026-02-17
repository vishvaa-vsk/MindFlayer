"""Code analyzer - extracts validation rules, enums, and business logic from source code.

Supports Python AST parsing to extract:
- Enum definitions (from enum.Enum)
- Pydantic model validators
- Business logic rules (from if/raise patterns)
- SQLAlchemy model constraints
"""
import ast
import re
import logging
from typing import Any

from models.context import (
    CodeContext,
    EnumDefinition,
    ValidatorRule,
    BusinessRule,
    ModelDefinition,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# Python AST Analyzer
# ═══════════════════════════════════════════════════════════


class PythonCodeVisitor(ast.NodeVisitor):
    """AST visitor to extract metadata from Python source code."""
    
    def __init__(self, filename: str = "<unknown>"):
        self.filename = filename
        self.enums: list[EnumDefinition] = []
        self.validators: list[ValidatorRule] = []
        self.business_rules: list[BusinessRule] = []
        self.models: list[ModelDefinition] = []
        self.current_class: str | None = None
    
    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        """Visit class definitions to extract enums and models."""
        self.current_class = node.name
        
        # Check if it's an Enum
        if self._is_enum_class(node):
            enum_def = self._extract_enum(node)
            if enum_def:
                self.enums.append(enum_def)
        
        # Check if it's a Pydantic model
        elif self._is_pydantic_model(node):
            model_def = self._extract_pydantic_model(node)
            if model_def:
                self.models.append(model_def)
        
        # Check if it's a SQLAlchemy model
        elif self._is_sqlalchemy_model(node):
            model_def = self._extract_sqlalchemy_model(node)
            if model_def:
                self.models.append(model_def)
        
        # Visit methods/functions inside the class
        self.generic_visit(node)
        self.current_class = None
    
    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        """Visit function definitions to extract business rules."""
        # Look for validator decorators in Pydantic models
        if self._has_validator_decorator(node):
            validators = self._extract_pydantic_validators(node)
            self.validators.extend(validators)
        
        # Extract business rules from if/raise patterns
        business_rules = self._extract_business_rules_from_function(node)
        self.business_rules.extend(business_rules)
        
        self.generic_visit(node)
    
    # ── Helper Methods ────────────────────────────────────
    
    def _is_enum_class(self, node: ast.ClassDef) -> bool:
        """Check if class inherits from Enum."""
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id in ("Enum", "IntEnum", "StrEnum"):
                return True
            if isinstance(base, ast.Attribute) and base.attr in ("Enum", "IntEnum", "StrEnum"):
                return True
        return False
    
    def _is_pydantic_model(self, node: ast.ClassDef) -> bool:
        """Check if class inherits from BaseModel."""
        for base in node.bases:
            if isinstance(base, ast.Name) and "BaseModel" in base.id:
                return True
            if isinstance(base, ast.Attribute) and base.attr == "BaseModel":
                return True
        return False
    
    def _is_sqlalchemy_model(self, node: ast.ClassDef) -> bool:
        """Check if class looks like SQLAlchemy model."""
        # Look for __tablename__ or Column definitions
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == "__tablename__":
                        return True
        return False
    
    def _extract_enum(self, node: ast.ClassDef) -> EnumDefinition | None:
        """Extract enum values from class definition."""
        values = []
        
        for item in node.body:
            # Enum members: NAME = "value" or NAME = auto()
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        # Get the member name
                        member_name = target.id
                        if member_name.isupper() or not member_name.startswith("_"):
                            # Try to get the value
                            value = self._get_constant_value(item.value)
                            if value is None:
                                value = member_name.lower()
                            values.append(value)
        
        if not values:
            return None
        
        # Extract description from docstring
        description = ast.get_docstring(node) or ""
        
        return EnumDefinition(
            name=node.name,
            values=values,
            source_file=self.filename,
            description=description.split('\n')[0] if description else ""
        )
    
    def _extract_pydantic_model(self, node: ast.ClassDef) -> ModelDefinition | None:
        """Extract field definitions from Pydantic model."""
        fields = {}
        validators = []
        
        for item in node.body:
            # Field annotations: name: str
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                field_name = item.target.id
                field_type = self._ast_to_type_string(item.annotation)
                fields[field_name] = field_type
                
                # Check for Field() with validators
                if item.value:
                    field_validators = self._extract_field_validators(field_name, item.value)
                    validators.extend(field_validators)
        
        if not fields:
            return None
        
        model_def = ModelDefinition(
            name=node.name,
            fields=fields,
            validators=validators,
            source_file=self.filename
        )
        
        return model_def
    
    def _extract_sqlalchemy_model(self, node: ast.ClassDef) -> ModelDefinition | None:
        """Extract field definitions from SQLAlchemy model."""
        fields = {}
        validators = []
        
        for item in node.body:
            # Column definitions: name = Column(String(50), nullable=False)
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        field_name = target.id
                        if field_name.startswith("_") or field_name == "__tablename__":
                            continue
                        
                        # Try to parse Column type
                        field_type = self._extract_column_type(item.value)
                        if field_type:
                            fields[field_name] = field_type
                            
                            # Extract constraints from Column
                            constraints = self._extract_column_constraints(field_name, item.value)
                            validators.extend(constraints)
        
        if not fields:
            return None
        
        return ModelDefinition(
            name=node.name,
            fields=fields,
            validators=validators,
            source_file=self.filename
        )
    
    def _has_validator_decorator(self, node: ast.FunctionDef) -> bool:
        """Check if function has @validator or @field_validator decorator."""
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name) and decorator.id in ("validator", "field_validator"):
                return True
            if isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Name) and decorator.func.id in ("validator", "field_validator"):
                    return True
        return False
    
    def _extract_pydantic_validators(self, node: ast.FunctionDef) -> list[ValidatorRule]:
        """Extract validator rules from Pydantic validator functions."""
        validators = []
        
        # Get field name from decorator
        field_name = None
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                if decorator.args:
                    arg = decorator.args[0]
                    if isinstance(arg, ast.Constant):
                        field_name = arg.value
        
        if not field_name:
            return validators
        
        # Analyze function body for validation logic
        for stmt in ast.walk(node):
            # Look for assertions or raises
            if isinstance(stmt, ast.Assert):
                error_msg = ""
                if stmt.msg:
                    error_msg = self._get_constant_value(stmt.msg) or ""
                validators.append(ValidatorRule(
                    field_name=field_name,
                    rule_type="assertion",
                    constraint=ast.unparse(stmt.test) if hasattr(ast, 'unparse') else str(stmt.test),
                    error_message=str(error_msg),
                    source_file=self.filename
                ))
            
            elif isinstance(stmt, ast.If):
                # Look for if condition followed by raise
                for child in ast.walk(stmt):
                    if isinstance(child, ast.Raise):
                        validators.append(ValidatorRule(
                            field_name=field_name,
                            rule_type="conditional",
                            constraint=ast.unparse(stmt.test) if hasattr(ast, 'unparse') else str(stmt.test),
                            error_message=self._extract_error_message(child),
                            source_file=self.filename
                        ))
        
        return validators
    
    def _extract_field_validators(self, field_name: str, value_node: ast.AST) -> list[ValidatorRule]:
        """Extract validators from Field() definitions."""
        validators = []
        
        if not isinstance(value_node, ast.Call):
            return validators
        
        # Check if it's Field() or similar
        func_name = None
        if isinstance(value_node.func, ast.Name):
            func_name = value_node.func.id
        
        if func_name not in ("Field", "Column"):
            return validators
        
        # Extract keyword arguments
        for keyword in value_node.keywords:
            arg_name = keyword.arg
            arg_value = self._get_constant_value(keyword.value)
            
            if arg_name in ("min_length", "max_length", "ge", "le", "gt", "lt"):
                validators.append(ValidatorRule(
                    field_name=field_name,
                    rule_type=arg_name,
                    constraint=arg_value,
                    source_file=self.filename
                ))
            
            elif arg_name == "regex" or arg_name == "pattern":
                validators.append(ValidatorRule(
                    field_name=field_name,
                    rule_type="pattern",
                    constraint=str(arg_value),
                    source_file=self.filename
                ))
        
        return validators
    
    def _extract_business_rules_from_function(self, node: ast.FunctionDef) -> list[BusinessRule]:
        """Extract business rules from if/raise patterns in methods."""
        rules = []
        
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.If):
                # Look for patterns like: if condition: raise Error("message")
                has_raise = any(isinstance(child, ast.Raise) for child in ast.walk(stmt))
                
                if has_raise:
                    condition = ast.unparse(stmt.test) if hasattr(ast, 'unparse') else str(stmt.test)
                    
                    # Find the raise statement
                    error_msg = ""
                    for child in ast.walk(stmt):
                        if isinstance(child, ast.Raise):
                            error_msg = self._extract_error_message(child)
                            break
                    
                    rules.append(BusinessRule(
                        description=f"Validation rule in {node.name}",
                        condition=condition,
                        action="raise_error",
                        error_message=error_msg,
                        applies_to=self.current_class or node.name,
                        source_file=self.filename
                    ))
        
        return rules
    
    def _extract_column_type(self, node: ast.AST) -> str | None:
        """Extract type from SQLAlchemy Column definition."""
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "Column":
                if node.args:
                    type_arg = node.args[0]
                    if isinstance(type_arg, ast.Name):
                        return type_arg.id.lower()
                    elif isinstance(type_arg, ast.Call) and isinstance(type_arg.func, ast.Name):
                        return type_arg.func.id.lower()
        return None
    
    def _extract_column_constraints(self, field_name: str, node: ast.AST) -> list[ValidatorRule]:
        """Extract constraints from SQLAlchemy Column."""
        validators = []
        
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg == "nullable":
                    value = self._get_constant_value(keyword.value)
                    if value is False:
                        validators.append(ValidatorRule(
                            field_name=field_name,
                            rule_type="required",
                            constraint=True,
                            source_file=self.filename
                        ))
        
        return validators
    
    def _extract_error_message(self, raise_node: ast.Raise) -> str:
        """Extract error message from raise statement."""
        if raise_node.exc:
            if isinstance(raise_node.exc, ast.Call):
                # raise ValueError("message")
                if raise_node.exc.args:
                    arg = raise_node.exc.args[0]
                    if isinstance(arg, ast.Constant):
                        return str(arg.value)
            elif isinstance(raise_node.exc, ast.Constant):
                return str(raise_node.exc.value)
        return ""
    
    def _get_constant_value(self, node: ast.AST) -> Any:
        """Extract constant value from AST node."""
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Name):
            return node.id
        return None
    
    def _ast_to_type_string(self, node: ast.AST) -> str:
        """Convert AST type annotation to string."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Constant):
            return str(node.value)
        elif hasattr(ast, 'unparse'):
            return ast.unparse(node)
        return "Any"


# ═══════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════


def analyze_python_file(file_content: str, filename: str = "<unknown>") -> CodeContext:
    """
    Analyze Python source code and extract metadata.
    
    Args:
        file_content: Python source code as string
        filename: Optional filename for tracking
    
    Returns:
        CodeContext with extracted enums, validators, business rules, models
    
    Raises:
        ValueError: If source code has syntax errors
    """
    try:
        tree = ast.parse(file_content)
    except SyntaxError as e:
        raise ValueError(f"Syntax error in {filename}: {e}")
    
    visitor = PythonCodeVisitor(filename=filename)
    visitor.visit(tree)
    
    return CodeContext(
        enums=visitor.enums,
        validators=visitor.validators,
        business_rules=visitor.business_rules,
        models=visitor.models
    )


def analyze_python_files(files: dict[str, str]) -> CodeContext:
    """
    Analyze multiple Python files and merge their contexts.
    
    Args:
        files: Dict mapping filename -> file_content
    
    Returns:
        Merged CodeContext from all files
    """
    merged = CodeContext()
    
    for filename, content in files.items():
        try:
            file_context = analyze_python_file(content, filename)
            merged.enums.extend(file_context.enums)
            merged.validators.extend(file_context.validators)
            merged.business_rules.extend(file_context.business_rules)
            merged.models.extend(file_context.models)
        except ValueError as e:
            logger.warning(f"Failed to parse {filename}: {e}")
            continue
    
    return merged


def analyze_code_files(files: dict[str, str], language: str = "python") -> CodeContext:
    """
    Analyze code files in specified language.
    
    Currently only supports Python. Future: Java, JavaScript, etc.
    
    Args:
        files: Dict mapping filename -> file_content
        language: Programming language (currently only "python")
    
    Returns:
        CodeContext with extracted metadata
    
    Raises:
        ValueError: If language is not supported
    """
    if language.lower() == "python":
        return analyze_python_files(files)
    else:
        raise ValueError(f"Unsupported language: {language}. Only 'python' is currently supported.")
