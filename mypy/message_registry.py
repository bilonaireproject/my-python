"""Message constants for generating error messages during type checking.

Literal messages should be defined as constants in this module so they won't get out of sync
if used in more than one place, and so that they can be easily introspected. These messages are
ultimately consumed by messages.MessageBuilder.fail(). For more non-trivial message generation,
add a method to MessageBuilder and call this instead.
"""

from typing import Optional
from typing_extensions import Final

from mypy import errorcodes as codes


class ErrorMessage:
    def __init__(self, value: str, code: Optional[codes.ErrorCode] = None) -> None:
        self.value = value
        self.code = code

    def __repr__(self) -> str:
        return '<ErrorMessage "{}">'.format(self.value)

    def format(self, *args: object, **kwargs: object) -> "ErrorMessage":
        return ErrorMessage(self.value.format(*args, **kwargs), code=self.code)


# Invalid types
INVALID_TYPE_RAW_ENUM_VALUE: Final = ErrorMessage("Invalid type: try using Literal[{}.{}] instead?")

# Type checker error message constants
NO_RETURN_VALUE_EXPECTED: Final = ErrorMessage("No return value expected", codes.RETURN_VALUE)
MISSING_RETURN_STATEMENT: Final = ErrorMessage("Missing return statement", codes.RETURN)
INVALID_IMPLICIT_RETURN: Final = ErrorMessage("Implicit return in function which does not return")
INCOMPATIBLE_RETURN_VALUE_TYPE: Final = "Incompatible return value type"
RETURN_VALUE_EXPECTED: Final = ErrorMessage("Return value expected", codes.RETURN_VALUE)
NO_RETURN_EXPECTED: Final = ErrorMessage("Return statement in function which does not return")
INVALID_EXCEPTION: Final = "Exception must be derived from BaseException"
INVALID_EXCEPTION_TYPE: Final = ErrorMessage("Exception type must be derived from BaseException")
RETURN_IN_ASYNC_GENERATOR: Final = ErrorMessage('"return" with value in async generator is not allowed')
INVALID_RETURN_TYPE_FOR_GENERATOR: Final = ErrorMessage(
    'The return type of a generator function should be "Generator"' " or one of its supertypes"
)
INVALID_RETURN_TYPE_FOR_ASYNC_GENERATOR: Final = ErrorMessage(
    'The return type of an async generator function should be "AsyncGenerator" or one of its '
    "supertypes"
)
INVALID_GENERATOR_RETURN_ITEM_TYPE: Final = ErrorMessage(
    "The return type of a generator function must be None in"
    " its third type parameter in Python 2"
)
YIELD_VALUE_EXPECTED: Final = ErrorMessage("Yield value expected")
INCOMPATIBLE_TYPES: Final = "Incompatible types"
INCOMPATIBLE_TYPES_IN_ASSIGNMENT: Final = "Incompatible types in assignment"
INCOMPATIBLE_REDEFINITION: Final = ErrorMessage("Incompatible redefinition")
INCOMPATIBLE_TYPES_IN_AWAIT: Final = 'Incompatible types in "await"'
INCOMPATIBLE_TYPES_IN_ASYNC_WITH_AENTER: Final = (
    'Incompatible types in "async with" for "__aenter__"'
)
INCOMPATIBLE_TYPES_IN_ASYNC_WITH_AEXIT: Final = (
    'Incompatible types in "async with" for "__aexit__"'
)
INCOMPATIBLE_TYPES_IN_ASYNC_FOR: Final = 'Incompatible types in "async for"'

INCOMPATIBLE_TYPES_IN_YIELD: Final = 'Incompatible types in "yield"'
INCOMPATIBLE_TYPES_IN_YIELD_FROM: Final = 'Incompatible types in "yield from"'
INCOMPATIBLE_TYPES_IN_STR_INTERPOLATION: Final = "Incompatible types in string interpolation"
MUST_HAVE_NONE_RETURN_TYPE: Final = ErrorMessage('The return type of "{}" must be None')
INVALID_TUPLE_INDEX_TYPE: Final = "Invalid tuple index type"
TUPLE_INDEX_OUT_OF_RANGE: Final = ErrorMessage("Tuple index out of range")
INVALID_SLICE_INDEX: Final = "Slice index must be an integer or None"
CANNOT_INFER_LAMBDA_TYPE: Final = ErrorMessage("Cannot infer type of lambda")
CANNOT_ACCESS_INIT: Final = ErrorMessage('Cannot access "__init__" directly')
NON_INSTANCE_NEW_TYPE: Final = ErrorMessage('"__new__" must return a class instance (got {})')
INVALID_NEW_TYPE: Final = 'Incompatible return type for "__new__"'
BAD_CONSTRUCTOR_TYPE: Final = ErrorMessage("Unsupported decorated constructor type")
CANNOT_ASSIGN_TO_METHOD: Final = ErrorMessage("Cannot assign to a method", codes.ASSIGNMENT)
CANNOT_ASSIGN_TO_TYPE: Final = ErrorMessage("Cannot assign to a type")
INCONSISTENT_ABSTRACT_OVERLOAD: Final = ErrorMessage(
    "Overloaded method has both abstract and non-abstract variants"
)
MULTIPLE_OVERLOADS_REQUIRED: Final = ErrorMessage("Single overload definition, multiple required")
READ_ONLY_PROPERTY_OVERRIDES_READ_WRITE: Final = ErrorMessage(
    "Read-only property cannot override read-write property"
)
FORMAT_REQUIRES_MAPPING: Final = "Format requires a mapping"
RETURN_TYPE_CANNOT_BE_CONTRAVARIANT: Final = ErrorMessage(
    "Cannot use a contravariant type variable as return type"
)
FUNCTION_PARAMETER_CANNOT_BE_COVARIANT: Final = ErrorMessage(
    "Cannot use a covariant type variable as a parameter"
)
INCOMPATIBLE_IMPORT_OF: Final = "Incompatible import of"
FUNCTION_TYPE_EXPECTED: Final = ErrorMessage("Function is missing a type annotation", codes.NO_UNTYPED_DEF)
ONLY_CLASS_APPLICATION: Final = ErrorMessage("Type application is only supported for generic classes")
RETURN_TYPE_EXPECTED: Final = ErrorMessage("Function is missing a return type annotation", codes.NO_UNTYPED_DEF)
ARGUMENT_TYPE_EXPECTED: Final = ErrorMessage("Function is missing a type annotation for one or more arguments", codes.NO_UNTYPED_DEF)
KEYWORD_ARGUMENT_REQUIRES_STR_KEY_TYPE: Final = ErrorMessage(
    'Keyword argument only valid with "str" key type in call to "dict"'
)
ALL_MUST_BE_SEQ_STR: Final = ErrorMessage("Type of __all__ must be {}, not {}")
INVALID_TYPEDDICT_ARGS: Final = ErrorMessage(
    "Expected keyword arguments, {...}, or dict(...) in TypedDict constructor"
)
TYPEDDICT_KEY_MUST_BE_STRING_LITERAL: Final = ErrorMessage("Expected TypedDict key to be string literal")
MALFORMED_ASSERT: Final = ErrorMessage("Assertion is always true, perhaps remove parentheses?")
DUPLICATE_TYPE_SIGNATURES: Final = ErrorMessage("Function has duplicate type signatures", codes.SYNTAX)
DESCRIPTOR_SET_NOT_CALLABLE: Final = ErrorMessage("{}.__set__ is not callable")
DESCRIPTOR_GET_NOT_CALLABLE: Final = ErrorMessage("{}.__get__ is not callable")
MODULE_LEVEL_GETATTRIBUTE: Final = ErrorMessage("__getattribute__ is not valid at the module level")

# Generic
GENERIC_INSTANCE_VAR_CLASS_ACCESS: Final = ErrorMessage(
    "Access to generic instance variables via class is ambiguous"
)
GENERIC_CLASS_VAR_ACCESS: Final = ErrorMessage("Access to generic class variables is ambiguous")
BARE_GENERIC: Final = ErrorMessage("Missing type parameters for generic type {}", codes.TYPE_ARG)
IMPLICIT_GENERIC_ANY_BUILTIN: Final = ErrorMessage(
    'Implicit generic "Any". Use "{}" and specify generic parameters', codes.TYPE_ARG
)

# TypeVar
INCOMPATIBLE_TYPEVAR_VALUE: Final = ErrorMessage('Value of type variable "{}" of {} cannot be {}', codes.TYPE_VAR)
CANNOT_USE_TYPEVAR_AS_EXPRESSION: Final = ErrorMessage('Type variable "{}.{}" cannot be used as an expression')

# Super
TOO_MANY_ARGS_FOR_SUPER: Final = ErrorMessage('Too many arguments for "super"')
TOO_FEW_ARGS_FOR_SUPER: Final = ErrorMessage('Too few arguments for "super"', codes.CALL_ARG)
SUPER_WITH_SINGLE_ARG_NOT_SUPPORTED: Final = ErrorMessage('"super" with a single argument not supported')
UNSUPPORTED_ARG_1_FOR_SUPER: Final = ErrorMessage('Unsupported argument 1 for "super"')
UNSUPPORTED_ARG_2_FOR_SUPER: Final = ErrorMessage('Unsupported argument 2 for "super"')
SUPER_VARARGS_NOT_SUPPORTED: Final = ErrorMessage('Varargs not supported with "super"')
SUPER_POSITIONAL_ARGS_REQUIRED: Final = ErrorMessage('"super" only accepts positional arguments')
SUPER_ARG_2_NOT_INSTANCE_OF_ARG_1: Final = ErrorMessage('Argument 2 for "super" not an instance of argument 1')
TARGET_CLASS_HAS_NO_BASE_CLASS: Final = ErrorMessage("Target class has no base class")
SUPER_OUTSIDE_OF_METHOD_NOT_SUPPORTED: Final = ErrorMessage("super() outside of a method is not supported")
SUPER_ENCLOSING_POSITIONAL_ARGS_REQUIRED: Final = ErrorMessage(
    "super() requires one or more positional arguments in enclosing function"
)

# Self-type
MISSING_OR_INVALID_SELF_TYPE: Final = ErrorMessage(
    "Self argument missing for a non-static method (or an invalid type for self)"
)
ERASED_SELF_TYPE_NOT_SUPERTYPE: Final =ErrorMessage(
    'The erased type of self "{}" is not a supertype of its class "{}"'
)
INVALID_SELF_TYPE_OR_EXTRA_ARG: Final = ErrorMessage(
    "Invalid type for self, or extra argument type in function annotation"
)

# Final
CANNOT_INHERIT_FROM_FINAL: Final = ErrorMessage('Cannot inherit from final class "{}"')
DEPENDENT_FINAL_IN_CLASS_BODY: Final = ErrorMessage(
    "Final name declared in class body cannot depend on type variables"
)
CANNOT_ACCESS_FINAL_INSTANCE_ATTR: Final = ErrorMessage(
    'Cannot access final instance attribute "{}" on class object'
)
CANNOT_MAKE_DELETABLE_FINAL: Final = ErrorMessage("Deletable attribute cannot be final")

# ClassVar
CANNOT_OVERRIDE_INSTANCE_VAR: Final = ErrorMessage(
    'Cannot override instance variable (previously declared on base class "{}") with class '
    "variable"
)
CANNOT_OVERRIDE_CLASS_VAR: Final = ErrorMessage(
    'Cannot override class variable (previously declared on base class "{}") with instance '
    "variable"
)

# Protocol
RUNTIME_PROTOCOL_EXPECTED: Final = ErrorMessage(
    "Only @runtime_checkable protocols can be used with instance and class checks"
)
CANNOT_INSTANTIATE_PROTOCOL: Final = ErrorMessage('Cannot instantiate protocol class "{}"')

CONTIGUOUS_ITERABLE_EXPECTED: Final = ErrorMessage("Contiguous iterable with same type expected")
ITERABLE_TYPE_EXPECTED: Final = ErrorMessage("Invalid type '{}' for *expr (iterable expected)")
TYPE_GUARD_POS_ARG_REQUIRED: Final = ErrorMessage("Type guard requires positional argument")
TOO_MANY_UNION_COMBINATIONS: Final = ErrorMessage("Not all union combinations were tried because there are too many unions")

# Type Analysis
TYPEANAL_INTERNAL_ERROR: Final = ErrorMessage('Internal error (node is None, kind={})')
NOT_SUBSCRIPTABLE: Final = ErrorMessage('"{}" is not subscriptable')
NOT_SUBSCRIPTABLE_REPLACEMENT: Final = ErrorMessage('"{}" is not subscriptable, use "{}" instead')
PARAMSPEC_UNBOUND: Final = ErrorMessage('ParamSpec "{}" is unbound')
PARAMSPEC_INVALID_LOCATION: Final = ErrorMessage('Invalid location for ParamSpec "{}"')
NO_BOUND_TYPEVAR_GENERIC_ALIAS: Final = ErrorMessage('Can\'t use bound type variable "{}" to define generic alias')
TYPEVAR_USED_WITH_ARGS: Final = ErrorMessage('Type variable "{}" used with arguments')
ONLY_OUTERMOST_FINAL: Final =  ErrorMessage("Final can be only used as an outermost qualifier in a variable annotation")
BUILTIN_TUPLE_NOT_DEFINED: Final = ErrorMessage('Name "tuple" is not defined')
SINGLE_TYPE_ARG: Final = ErrorMessage('{} must have exactly one type argument')
INVALID_NESTED_CLASSVAR: Final = ErrorMessage('Invalid type: ClassVar nested inside other type')
CLASSVAR_ATMOST_ONE_TYPE_ARG: Final = ErrorMessage('ClassVar[...] must have at most one type argument')
ANNOTATED_SINGLE_TYPE_ARG: Final = ErrorMessage('Annotated[...] must have exactly one type argument and at least one annotation')
GENERIC_TUPLE_UNSUPPORTED: Final = ErrorMessage('Generic tuple types not supported')
GENERIC_TYPED_DICT_UNSUPPORTED: Final = ErrorMessage('Generic TypedDict types not supported')
VARIABLE_NOT_VALID_TYPE: Final = ErrorMessage('Variable "{}" is not valid as a type', codes.VALID_TYPE)
FUNCTION_NOT_VALID_TYPE: Final = ErrorMessage('Function "{}" is not valid as a type', codes.VALID_TYPE)
MODULE_NOT_VALID_TYPE: Final = ErrorMessage('Module "{}" is not valid as a type', codes.VALID_TYPE)
UNBOUND_TYPEVAR: Final = ErrorMessage('Type variable "{}" is unbound', codes.VALID_TYPE)
CANNOT_INTERPRET_AS_TYPE: Final = ErrorMessage('Cannot interpret reference "{}" as a type', codes.VALID_TYPE)
INVALID_TYPE: Final = ErrorMessage('Invalid type')
BRACKETED_EXPR_INVALID_TYPE: Final = ErrorMessage('Bracketed expression "[...]" is not valid as a type')
ANNOTATION_SYNTAX_ERROR: Final = ErrorMessage('Syntax error in type annotation', codes.SYNTAX)
TUPLE_SINGLE_STAR_TYPE: Final = ErrorMessage('At most one star type allowed in a tuple')
INVALID_TYPE_USE_LITERAL: Final = ErrorMessage("Invalid type: try using Literal[{}] instead?", codes.VALID_TYPE)
INVALID_LITERAL_TYPE: Final = ErrorMessage("Invalid type: {} literals cannot be used as a type", codes.VALID_TYPE)
INVALID_ANNOTATION: Final = ErrorMessage('Invalid type comment or annotation', codes.VALID_TYPE)
PIPE_UNION_REQUIRES_PY310: Final = ErrorMessage("X | Y syntax for unions requires Python 3.10")
UNEXPECTED_ELLIPSIS: Final = ErrorMessage('Unexpected "..."')
CALLABLE_INVALID_FIRST_ARG: Final = ErrorMessage('The first argument to Callable must be a list of types or "..."')
CALLABLE_INVALID_ARGS: Final = ErrorMessage('Please use "Callable[[<parameters>], <return type>]" or "Callable"')
INVALID_ARG_CONSTRUCTOR: Final = ErrorMessage('Invalid argument constructor "{}"')
ARGS_SHOULD_NOT_HAVE_NAMES: Final = ErrorMessage("{} arguments should not have names")
LITERAL_AT_LEAST_ONE_ARG: Final = ErrorMessage('Literal[...] must have at least one parameter')
LITERAL_INDEX_CANNOT_BE_ANY: Final = ErrorMessage('Parameter {} of Literal[...] cannot be of type "Any"')
LITERAL_INDEX_INVALID_TYPE: Final = ErrorMessage('Parameter {} of Literal[...] cannot be of type "{}"')
LITERAL_INVALID_EXPRESSION: Final = ErrorMessage('Invalid type: Literal[...] cannot contain arbitrary expressions')
LITERAL_INVALID_PARAMETER: Final = ErrorMessage('Parameter {} of Literal[...] is invalid')
TYPEVAR_BOUND_BY_OUTER_CLASS: Final = ErrorMessage('Type variable "{}" is bound by an outer class')
TYPE_ARG_COUNT_MISMATCH: Final = ErrorMessage('"{}" expects {}, but {} given', codes.TYPE_ARG)
TYPE_ALIAS_ARG_COUNT_MISMATCH: Final = ErrorMessage('Bad number of arguments for type alias, expected: {}, given: {}')

# function definitions, from nodes.py
DUPLICATE_ARGUMENT_IN_X: Final = ErrorMessage('Duplicate argument "{}" in {}')
POS_ARGS_BEFORE_DEFAULT_NAMED_OR_VARARGS: Final = ErrorMessage("Required positional args may not appear after default, named or var args")
DEFAULT_ARGS_BEFORE_NAMED_OR_VARARGS: Final = ErrorMessage("Positional default args may not appear after named or var args")
VAR_ARGS_BEFORE_NAMED_OR_VARARGS: Final = ErrorMessage("Var args may not appear after named or var args")
KWARGS_MUST_BE_LAST: Final = ErrorMessage("A **kwargs argument must be the last argument")
MULTIPLE_KWARGS: Final = ErrorMessage("You may only have one **kwargs argument")

# from type_anal_hook.py
INVALID_SIGNAL_TYPE: Final = ErrorMessage('Invalid "Signal" type (expected "Signal[[t, ...]]")')

# NewType
NEWTYPE_USED_WITH_PROTOCOL: Final = ErrorMessage("NewType cannot be used with protocol classes")
NEWTYPE_ARG_MUST_BE_SUBCLASSABLE: Final = ErrorMessage("Argument 2 to NewType(...) must be subclassable (got {})", codes.VALID_NEWTYPE)
CANNOT_DECLARE_TYPE_OF_NEWTYPE: Final = ErrorMessage("Cannot declare the type of a NewType declaration")
CANNOT_REDEFINE_AS_NEWTYPE: Final = ErrorMessage('Cannot redefine "{}" as a NewType')
NEWTYPE_EXPECTS_TWO_ARGS: Final = ErrorMessage("NewType(...) expects exactly two positional arguments")
NEWTYPE_ARG_STRING_LITERAL: Final = ErrorMessage("Argument 1 to NewType(...) must be a string literal")
NEWTYPE_ARG_VARNAME_MISMATCH: Final = ErrorMessage('String argument 1 "{}" to NewType(...) does not match variable name "{}"')
NEWTYPE_ARG_INVALID_TYPE: Final = ErrorMessage("Argument 2 to NewType(...) must be a valid type")

# TypedDict
TYPEDDICT_BASES_MUST_BE_TYPEDDICTS: Final = ErrorMessage("All bases of a new TypedDict must be TypedDict types")
TYPEDDICT_OVERWRITE_FIELD_IN_MERGE: Final = ErrorMessage('Overwriting TypedDict field "{}" while merging')
TYPEDDICT_OVERWRITE_FIELD_IN_EXTEND: Final = ErrorMessage('Overwriting TypedDict field "{}" while extending')
TYPEDDICT_CLASS_ERROR: Final = ErrorMessage(
    "Invalid statement in TypedDict definition; " 'expected "field_name: field_type"'
)
TYPEDDICT_ARG_NAME_MISMATCH: Final = ErrorMessage('First argument "{}" to TypedDict() does not match variable name "{}"', codes.NAME_MATCH)
TYPEDDICT_TOO_FEW_ARGS: Final = ErrorMessage("Too few arguments for TypedDict()")
TYPEDDICT_TOO_MANY_ARGS: Final = ErrorMessage("Too many arguments for TypedDict()")
TYPEDDICT_UNEXPECTED_ARGS: Final = ErrorMessage("Unexpected arguments to TypedDict()")
TYPEDDICT_CALL_UNEXPECTED_KWARG: Final = ErrorMessage('Unexpected keyword argument "{}" for "TypedDict"')
TYPEDDICT_CALL_EXPECTED_STRING_LITERAL: Final = ErrorMessage("TypedDict() expects a string literal as the first argument")
TYPEDDICT_CALL_EXPECTED_DICT: Final = ErrorMessage("TypedDict() expects a dictionary literal as the second argument")
TYPEDDICT_RHS_VALUE_UNSUPPORTED: Final = ErrorMessage('Right hand side values are not supported in TypedDict')
TYPEDDICT_TOTAL_MUST_BE_BOOL: Final = ErrorMessage('TypedDict() "total" argument must be True or False')
TYPEDDICT_TOTAL_MUST_BE_BOOL_2: Final = ErrorMessage('Value of "total" must be True or False')
TYPEDDICT_DUPLICATE_KEY: Final = ErrorMessage('Duplicate TypedDict key "{}"')
TYPEDDICT_INVALID_FIELD_NAME: Final = ErrorMessage("Invalid TypedDict() field name")
TYPEDDICT_INVALID_FIELD_TYPE: Final = ErrorMessage('Invalid field type')

# Enum
ENUM_ATTRIBUTE_UNSUPPORTED: Final = ErrorMessage("Enum type as attribute is not supported")
ENUM_CALL_UNEXPECTED_ARGS: Final = ErrorMessage("Unexpected arguments to {}()")
ENUM_CALL_UNEXPECTED_KWARG: Final = ErrorMessage('Unexpected keyword argument "{}"')
ENUM_CALL_TOO_MANY_ARGS: Final = ErrorMessage("Too many arguments for {}()")
ENUM_CALL_TOO_FEW_ARGS: Final = ErrorMessage("Too few arguments for {}()")
ENUM_CALL_EXPECTED_STRING_LITERAL: Final = ErrorMessage("{}() expects a string literal as the first argument")
ENUM_CALL_EXPECTED_STRINGS_OR_PAIRS: Final = ErrorMessage("{}() with tuple or list expects strings or (name, value) pairs")
ENUM_CALL_DICT_EXPECTED_STRING_KEYS: Final = ErrorMessage("{}() with dict literal requires string literals")
ENUM_CALL_EXPECTED_LITERAL: Final = ErrorMessage("{}() expects a string, tuple, list or dict literal as the second argument")
ENUM_CALL_ATLEAST_ONE_ITEM: Final = ErrorMessage("{}() needs at least one item")

# NamedTuple
NAMEDTUPLE_SUPPORTED_ABOVE_PY36: Final = ErrorMessage('NamedTuple class syntax is only supported in Python 3.6')
NAMEDTUPLE_SINGLE_BASE: Final = ErrorMessage('NamedTuple should be a single base')
NAMEDTUPLE_CLASS_ERROR: Final = ErrorMessage(
    "Invalid statement in NamedTuple definition; " 'expected "field_name: field_type [= default]"'
)
NAMEDTUPLE_FIELD_NO_UNDERSCORE: Final = ErrorMessage('NamedTuple field name cannot start with an underscore: {}')
NAMEDTUPLE_FIELD_DEFAULT_AFTER_NONDEFAULT: Final = ErrorMessage('Non-default NamedTuple fields cannot follow default fields')
NAMEDTUPLE_TOO_FEW_ARGS: Final = ErrorMessage("Too few arguments for namedtuple()")
NAMEDTUPLE_TOO_MANY_ARGS: Final = ErrorMessage("Too many arguments for namedtuple()")
NAMEDTUPLE_EXPECTED_LIST_TUPLE_DEFAULTS: Final = ErrorMessage("List or tuple literal expected as the defaults argument to namedtuple()")
NAMEDTUPLE_UNEXPECTED_ARGS: Final = ErrorMessage("Unexpected arguments to namedtuple()")
NAMEDTUPLE_ARG_EXPECTED_STRING_LITERAL : Final = ErrorMessage("namedtuple() expects a string literal as the first argument")
NAMEDTUPLE_ARG_EXPECTED_LIST_TUPLE: Final = ErrorMessage("List or tuple literal expected as the second argument to namedtuple()")
NAMEDTUPLE_EXPECTED_STRING_LITERAL : Final = ErrorMessage("String literal expected as namedtuple() item")
NAMEDTUPLE_FIELDS_NO_UNDERSCORE: Final = ErrorMessage("namedtuple() field names cannot start with an underscore: {}")
NAMEDTUPLE_TOO_MANY_DEFAULTS: Final = ErrorMessage("Too many defaults given in call to namedtuple()")
NAMEDTUPLE_INVALID_FIELD_DEFINITION: Final = ErrorMessage("Invalid NamedTuple field definition")
NAMEDTUPLE_INVALID_FIELD_NAME: Final = ErrorMessage("Invalid NamedTuple() field name")
NAMEDTUPLE_INVALID_FIELD_TYPE: Final = ErrorMessage('Invalid field type')
NAMEDTUPLE_TUPLE_EXPECTED: Final = ErrorMessage("Tuple expected as NamedTuple() field")
NAMEDTUPLE_CANNOT_OVERWRITE_ATTRIBUTE: Final = ErrorMessage('Cannot overwrite NamedTuple attribute "{}"')

# TypeArgs
TYPEVAR_INVALID_TYPE_ARG: Final = ErrorMessage('Type variable "{}" not valid as type argument value for "{}"', codes.TYPE_VAR)
TYPE_ARG_INVALID_SUBTYPE: Final = ErrorMessage('Type argument "{}" of "{}" must be a subtype of "{}"', codes.TYPE_VAR)
TYPE_ARG_INVALID_VALUE: Final = ErrorMessage('Invalid type argument value for "{}"', codes.TYPE_VAR)

# FastParse
TYPE_COMMENT_SYNTAX_ERROR: Final = ErrorMessage("syntax error in type comment", codes.SYNTAX)
TYPE_COMMENT_SYNTAX_ERROR_VALUE: Final = ErrorMessage('syntax error in type comment "{}"', codes.SYNTAX)
INVALID_TYPE_IGNORE: Final = ErrorMessage('Invalid "type: ignore" comment', codes.SYNTAX)
ELLIPSIS_WITH_OTHER_TYPEARGS: Final = ErrorMessage("Ellipses cannot accompany other argument types in function type signature", codes.SYNTAX)
TYPE_SIGNATURE_TOO_MANY_ARGS: Final = ErrorMessage('Type signature has too many arguments', codes.SYNTAX)
TYPE_SIGNATURE_TOO_FEW_ARGS: Final = ErrorMessage('Type signature has too few arguments', codes.SYNTAX)
ARG_CONSTRUCTOR_NAME_EXPECTED: Final = ErrorMessage("Expected arg constructor name", codes.SYNTAX)
ARG_CONSTRUCTOR_TOO_MANY_ARGS: Final = ErrorMessage("Too many arguments for argument constructor", codes.SYNTAX)
MULTIPLE_VALUES_FOR_NAME_KWARG: Final = ErrorMessage('"{}" gets multiple values for keyword argument "name"', codes.SYNTAX)
MULTIPLE_VALUES_FOR_TYPE_KWARG: Final = ErrorMessage('"{}" gets multiple values for keyword argument "type"', codes.SYNTAX)
ARG_CONSTRUCTOR_UNEXPECTED_ARG: Final = ErrorMessage('Unexpected argument "{}" for argument constructor', codes.SYNTAX)
ARG_NAME_EXPECTED_STRING_LITERAL: Final = ErrorMessage('Expected string literal for argument name, got {}', codes.SYNTAX)
EXCEPT_EXPR_NOTNAME_UNSIPPORTED: Final = ErrorMessage('Sorry, "except <expr>, <anything but a name>" is not supported', codes.SYNTAX)

# strings from messages.py
MEMBER_NOT_ASSIGNABLE: Final = ErrorMessage('Member "{}" is not assignable')
UNSUPPORTED_OPERAND_FOR_IN: Final = ErrorMessage('Unsupported right operand type for in ({})', codes.OPERATOR)
UNSUPPORTED_OPERAND_FOR_UNARY_MINUS: Final = ErrorMessage('Unsupported operand type for unary - ({})', codes.OPERATOR)
UNSUPPORTED_OPERAND_FOR_UNARY_PLUS: Final = ErrorMessage('Unsupported operand type for unary + ({})', codes.OPERATOR)
UNSUPPORTED_OPERAND_FOR_INVERT: Final = ErrorMessage('Unsupported operand type for ~ ({})', codes.OPERATOR)
TYPE_NOT_GENERIC_OR_INDEXABLE: Final = ErrorMessage('The type {} is not generic and not indexable')
TYPE_NOT_INDEXABLE: Final = ErrorMessage('Value of type {} is not indexable', codes.INDEX)
UNSUPPORTED_TARGET_INDEXED_ASSIGNMENT: Final = ErrorMessage('Unsupported target for indexed assignment ({})', codes.INDEX)
CALLING_FUNCTION_OF_UNKNOWN_TYPE: Final = ErrorMessage('Cannot call function of unknown type', codes.OPERATOR)
TYPE_NOT_CALLABLE: Final = ErrorMessage('{} not callable', codes.OPERATOR)
TYPE_HAS_NO_ATTRIBUTE_X_MAYBE_Y: Final = ErrorMessage('{} has no attribute "{}"; maybe {}?{}', codes.ATTR_DEFINED)
TYPE_HAS_NO_ATTRIBUTE_X: Final = ErrorMessage('{} has no attribute "{}"{}', codes.ATTR_DEFINED)
ITEM_HAS_NO_ATTRIBUTE_X: Final = ErrorMessage('Item {} of {} has no attribute "{}"{}', codes.UNION_ATTR)
UNSUPPORTED_OPERANDS_LIKELY_UNION: Final = ErrorMessage('Unsupported operand types for {} (likely involving Union)', codes.OPERATOR)
UNSUPPORTED_OPERANDS: Final = ErrorMessage('Unsupported operand types for {} ({} and {})', codes.OPERATOR)
UNSUPPORTED_LEFT_OPERAND_TYPE_UNION: Final = ErrorMessage('Unsupported left operand type for {} (some union)', codes.OPERATOR)
UNSUPPORTED_LEFT_OPERAND_TYPE: Final = ErrorMessage('Unsupported left operand type for {} ({})', codes.OPERATOR)
UNTYPED_FUNCTION_CALL: Final = ErrorMessage('Call to untyped function {} in typed context', codes.NO_UNTYPED_CALL)
INVALID_INDEX_TYPE: Final = ErrorMessage('Invalid index type {} for {}; expected type {}', codes.INDEX)
TARGET_INCOMPATIBLE_TYPE: Final = ErrorMessage('{} (expression has type {}, target has type {})', codes.ASSIGNMENT)
LIST_ITEM_INCOMPATIBLE_TYPE: Final = ErrorMessage('{} item {} has incompatible type {}; expected {}', codes.LIST_ITEM)
DICT_ENTRY_INCOMPATIBLE_TYPE: Final = ErrorMessage('{} entry {} has incompatible type {}: {}; expected {}: {}', codes.DICT_ITEM)
LIST_COMP_INCOMPATIBLE_TYPE: Final = ErrorMessage('List comprehension has incompatible type List[{}]; expected List[{}]')
SET_COMP_INCOMPATIBLE_TYPE: Final = ErrorMessage('Set comprehension has incompatible type Set[{}]; expected Set[{}]')
DICT_COMP_INCOMPATIBLE_TYPE: Final = ErrorMessage('{} expression in dictionary comprehension has incompatible type {}; expected type {}')
GENERATOR_INCOMPATIBLE_TYPE: Final = ErrorMessage('Generator has incompatible item type {}; expected {}')
MULTIPLE_VALUES_FOR_KWARG: Final = ErrorMessage('{} gets multiple values for keyword argument "{}"')
NO_RETURN_VALUE: Final = ErrorMessage('{} does not return a value', codes.FUNC_RETURNS_VALUE)
FUNCTION_NO_RETURN_VALUE: Final = ErrorMessage('Function does not return a value', codes.FUNC_RETURNS_VALUE)
UNDERSCORE_FUNCTION_CALL: Final = ErrorMessage('Calling function named "_" is not allowed')
READING_DELETED_VALUE: Final = ErrorMessage('Trying to read deleted variable{}')
ASSIGNMENT_OUTSIDE_EXCEPT: Final = ErrorMessage('Assignment to variable{} outside except: block')
OVERLOADS_REQUIRE_ATLEAST_ONE_ARG: Final = ErrorMessage('All overload variants{} require at least one argument')
UNPACK_MORE_THAN_ONE_VALUE_NEEDED: Final = ErrorMessage('Need more than 1 value to unpack ({} expected)')
UNPACK_TOO_FEW_VALUES: Final = ErrorMessage('Need more than {} values to unpack ({} expected)')
UNPACK_TOO_MANY_VALUES: Final = ErrorMessage('Too many values to unpack ({} expected, {} provided)')
UNPACKING_STRINGS_DISALLOWED: Final = ErrorMessage("Unpacking a string is disallowed")
TYPE_NOT_ITERABLE: Final = ErrorMessage('"{}" object is not iterable')
INCOMPATIBLE_OPERATOR_ASSIGNMENT: Final = ErrorMessage('Result type of {} incompatible in assignment')
OVERLOAD_SIGNATURE_INCOMPATIBLE: Final = ErrorMessage('Signature of "{}" incompatible with {}', codes.OVERRIDE)
SIGNATURE_INCOMPATIBLE_WITH_SUPERTYPE: Final = ErrorMessage('Signature of "{}" incompatible with {}', codes.OVERRIDE)
ARG_INCOMPATIBLE_WITH_SUPERTYPE: Final = ErrorMessage('Argument {} of "{}" is incompatible with {}; supertype defines the argument type as "{}"', codes.OVERRIDE)
RETURNTYPE_INCOMPATIBLE_WITH_SUPERTYPE: Final = ErrorMessage('Return type {} of "{}" incompatible with return type {} in {}', codes.OVERRIDE)
TYPE_APPLICATION_ON_NON_GENERIC_TYPE: Final = ErrorMessage('Type application targets a non-generic function or class')
TYPE_APPLICATION_TOO_MANY_TYPES: Final = ErrorMessage('Type application has too many types ({} expected)')
TYPE_APPLICATION_TOO_FEW_TYPES: Final = ErrorMessage('Type application has too few types ({} expected)')
CANNOT_INFER_TYPE_ARG_NAMED_FUNC: Final = ErrorMessage('Cannot infer type argument {} of {}')
CANNOT_INFER_TYPE_ARG_FUNC: Final = ErrorMessage('Cannot infer function type argument')
INVALID_VAR_ARGS: Final = ErrorMessage('List or tuple expected as variable arguments')
KEYWORDS_MUST_BE_STRINGS: Final = ErrorMessage('Keywords must be strings')
ARG_MUST_BE_MAPPING: Final = ErrorMessage('Argument after ** must be a mapping{}', codes.ARG_TYPE)
MEMBER_UNDEFINED_IN_SUPERCLASS: Final = ErrorMessage('"{}" undefined in superclass')
SUPER_ARG_EXPECTED_TYPE: Final = ErrorMessage('Argument 1 for "super" must be a type object; got {}', codes.ARG_TYPE)
FORMAT_STR_TOO_FEW_ARGS: Final = ErrorMessage('Not enough arguments for format string', codes.STRING_FORMATTING)
FORMAT_STR_TOO_MANY_ARGS: Final = ErrorMessage('Not all arguments converted during string formatting', codes.STRING_FORMATTING)
FORMAT_STR_UNSUPPORTED_CHAR: Final = ErrorMessage('Unsupported format character "{}"', codes.STRING_FORMATTING)
STRING_INTERPOLATION_WITH_STAR_AND_KEY: Final = ErrorMessage('String interpolation contains both stars and mapping keys', codes.STRING_FORMATTING)
FORMAT_STR_INVALID_CHR_CONVERSION_RANGE: Final = ErrorMessage('"{}c" requires an integer in range(256) or a single byte', codes.STRING_FORMATTING)
FORMAT_STR_INVALID_CHR_CONVERSION: Final = ErrorMessage('"{}c" requires int or char', codes.STRING_FORMATTING)
KEY_NOT_IN_MAPPING: Final = ErrorMessage('Key "{}" not found in mapping', codes.STRING_FORMATTING)
FORMAT_STR_MIXED_KEYS_AND_NON_KEYS: Final = ErrorMessage('String interpolation mixes specifier with and without mapping keys', codes.STRING_FORMATTING)
CANNOT_DETERMINE_TYPE: Final = ErrorMessage('Cannot determine type of "{}"', codes.HAS_TYPE)
CANNOT_DETERMINE_TYPE_IN_BASE: Final = ErrorMessage('Cannot determine type of "{}" in base class "{}"')
DOES_NOT_ACCEPT_SELF: Final = ErrorMessage('Attribute function "{}" with type {} does not accept self argument')
INCOMPATIBLE_SELF_ARG: Final = ErrorMessage('Invalid self argument {} to {} "{}" with type {}')
INCOMPATIBLE_CONDITIONAL_FUNCS: Final = ErrorMessage('All conditional function variants must have identical signatures')
CANNOT_INSTANTIATE_ABSTRACT_CLASS: Final = ErrorMessage('Cannot instantiate abstract class "{}" with abstract attribute{} {}', codes.ABSTRACT)
INCOMPATIBLE_BASE_CLASS_DEFNS: Final = ErrorMessage('Definition of "{}" in base class "{}" is incompatible with definition in base class "{}"')
CANNOT_ASSIGN_TO_CLASSVAR: Final = ErrorMessage('Cannot assign to class variable "{}" via instance')
CANNOT_OVERRIDE_TO_FINAL: Final = ErrorMessage('Cannot override writable attribute "{}" with a final one')
CANNOT_OVERRIDE_FINAL: Final = ErrorMessage('Cannot override final attribute "{}" (previously declared in base class "{}")')
CANNOT_ASSIGN_TO_FINAL: Final = ErrorMessage('Cannot assign to final {} "{}"')
PROTOCOL_MEMBER_CANNOT_BE_FINAL: Final = ErrorMessage("Protocol member cannot be final")
FINAL_WITHOUT_VALUE: Final = ErrorMessage("Final name must be initialized with a value")
PROPERTY_IS_READ_ONLY: Final = ErrorMessage('Property "{}" defined in "{}" is read-only')
NON_OVERLAPPING_COMPARISON: Final = ErrorMessage('Non-overlapping {} check ({} type: {}, {} type: {})', codes.COMPARISON_OVERLAP)
OVERLOAD_INCONSISTENT_DECORATOR_USE: Final = ErrorMessage('Overload does not consistently use the "@{}" decorator on all function signatures.')
OVERLOAD_INCOMPATIBLE_RETURN_TYPES: Final = ErrorMessage('Overloaded function signatures {} and {} overlap with incompatible return types')
OVERLOAD_SIGNATURE_WILL_NEVER_MATCH: Final = ErrorMessage('Overloaded function signature {index2} will never be matched: signature {index1}\'s parameter type(s) are the same or broader')
OVERLOAD_INCONSISTENT_TYPEVARS: Final = ErrorMessage('Overloaded function implementation cannot satisfy signature {} due to inconsistencies in how they use type variables')
OVERLOAD_INCONSISTENT_ARGS: Final = ErrorMessage('Overloaded function implementation does not accept all possible arguments of signature {}')
OVERLOAD_INCONSISTENT_RETURN_TYPE: Final = ErrorMessage('Overloaded function implementation cannot produce return type of signature {}')
OPERATOR_METHOD_SIGNATURE_OVERLAP: Final = ErrorMessage('Signatures of "{}" of "{}" and "{}" of {} are unsafely overlapping')
FORWARD_OPERATOR_NOT_CALLABLE: Final = ErrorMessage('Forward operator "{}" is not callable')
INCOMPATIBLE_SIGNATURES: Final = ErrorMessage('Signatures of "{}" and "{}" are incompatible')
INVALID_YIELD_FROM: Final = ErrorMessage('"yield from" can\'t be applied to {}')
INVALID_SIGNATURE: Final = ErrorMessage('Invalid signature "{}"')
INVALID_SIGNATURE_SPECIAL: Final = ErrorMessage('Invalid signature "{}" for "{}"')
UNSUPPORTED_TYPE_TYPE: Final = ErrorMessage('Cannot instantiate type "Type[{}]"')
REDUNDANT_CAST: Final = ErrorMessage('Redundant cast to {}', codes.REDUNDANT_CAST)
UNFOLLOWED_IMPORT: Final = ErrorMessage("{} becomes {} due to an unfollowed import", codes.NO_ANY_UNIMPORTED)
ANNOTATION_NEEDED: Final = ErrorMessage('Need type {} for "{}"{}', codes.VAR_ANNOTATED)
NO_EXPLICIT_ANY: Final = ErrorMessage('Explicit "Any" is not allowed')
TYPEDDICT_MISSING_KEYS: Final = ErrorMessage('Missing {} for TypedDict {}', codes.TYPEDDICT_ITEM)
TYPEDDICT_EXTRA_KEYS: Final = ErrorMessage('Extra {} for TypedDict {}', codes.TYPEDDICT_ITEM)
TYPEDDICT_UNEXPECTED_KEYS: Final = ErrorMessage('Unexpected TypedDict {}')
TYPEDDICT_KEYS_MISMATCH: Final = ErrorMessage('Expected {} but found {}', codes.TYPEDDICT_ITEM)
TYPEDDICT_KEY_STRING_LITERAL_EXPECTED: Final = ErrorMessage('TypedDict key must be a string literal; expected one of {}')
TYPEDDICT_KEY_INVALID: Final = ErrorMessage('"{}" is not a valid TypedDict key; expected one of {}')
TYPEDDICT_UNKNOWN_KEY: Final = ErrorMessage('TypedDict {} has no key "{}"', codes.TYPEDDICT_ITEM)
TYPEDDICT_AMBIGUOUS_TYPE: Final = ErrorMessage('Type of TypedDict is ambiguous, could be any of ({})')
TYPEDDICT_CANNOT_DELETE_KEY: Final = ErrorMessage('TypedDict key "{}" cannot be deleted')
TYPEDDICT_NAMED_CANNOT_DELETE_KEY: Final = ErrorMessage('Key "{}" of TypedDict {} cannot be deleted')
TYPEDDICT_INCONSISTENT_SETDEFAULT_ARGS: Final = ErrorMessage('Argument 2 to "setdefault" of "TypedDict" has incompatible type {}; expected {}', codes.TYPEDDICT_ITEM)
PARAMETERIZED_GENERICS_DISALLOWED: Final = ErrorMessage('Parameterized generics cannot be used with class or instance checks')
EXPR_HAS_ANY_TYPE: Final = ErrorMessage('Expression has type "Any"')
EXPR_CONTAINS_ANY_TYPE: Final = ErrorMessage('Expression type contains "Any" (has type {})')
INCORRECTLY_RETURNING_ANY: Final = ErrorMessage('Returning Any from function declared to return {}', codes.NO_ANY_RETURN)
INVALID_EXIT_RETURN_TYPE: Final = ErrorMessage('"bool" is invalid as return type for "__exit__" that always returns False', codes.EXIT_RETURN)
UNTYPED_DECORATOR_FUNCTION: Final = ErrorMessage("Function is untyped after decorator transformation")
DECORATED_TYPE_CONTAINS_ANY: Final = ErrorMessage('Type of decorated function contains type "Any" ({})')
DECORATOR_MAKES_FUNCTION_UNTYPED: Final = ErrorMessage('Untyped decorator makes function "{}" untyped')
CONCRETE_ONLY_ASSIGN: Final = ErrorMessage("Can only assign concrete classes to a variable of type {}")
EXPECTED_CONCRETE_CLASS: Final = ErrorMessage("Only concrete class can be given where {} is expected")
CANNOT_USE_FUNCTION_WITH_TYPE: Final = ErrorMessage("Cannot use {}() with {} type")
ISSUBCLASS_ONLY_NON_METHOD_PROTOCOL: Final = ErrorMessage("Only protocols that don't have non-method members can be used with issubclass()")
UNREACHABLE_STATEMENT: Final = ErrorMessage("Statement is unreachable", codes.UNREACHABLE)
UNREACHABLE_RIGHT_OPERAND: Final = ErrorMessage('Right operand of "{}" is never evaluated', codes.UNREACHABLE)
EXPR_IS_ALWAYS_BOOL: Final = ErrorMessage("{} is always {}", codes.REDUNDANT_EXPR)
IMPOSSIBLE_SUBCLASS: Final = ErrorMessage("Subclass of {} cannot exist: would have {}")

# String formatting checks
FORMAT_STR_INVALID_SPECIFIER: Final = ErrorMessage('Invalid conversion specifier in format string', codes.STRING_FORMATTING)
FORMAT_STR_BRACES_IN_SPECIFIER: Final = ErrorMessage('Conversion value must not contain { or }', codes.STRING_FORMATTING)
FORMAT_STR_NESTING_ATMOST_TWO_LEVELS: Final = ErrorMessage('Formatting nesting must be at most two levels deep', codes.STRING_FORMATTING)
FORMAT_STR_UNEXPECTED_RBRACE: Final = ErrorMessage('Invalid conversion specifier in format string: unexpected }', codes.STRING_FORMATTING)
FORMAT_STR_UNMATCHED_LBRACE: Final = ErrorMessage('Invalid conversion specifier in format string: unmatched {', codes.STRING_FORMATTING)
UNRECOGNIZED_FORMAT_SPEC: Final = ErrorMessage('Unrecognized format specification "{}"', codes.STRING_FORMATTING)
FORMAT_STR_INVALID_CONVERSION_TYPE: Final = ErrorMessage('Invalid conversion type "{}", must be one of "r", "s" or "a"', codes.STRING_FORMATTING)
FORMAT_STR_BYTES_USE_REPR: Final = ErrorMessage("On Python 3 '{}'.format(b'abc') produces \"b'abc'\", not 'abc'; use '{!r}'.format(b'abc') if this is desired behavior", codes.STR_BYTES_PY3)
FORMAT_STR_BYTES_USE_REPR_OLD: Final = ErrorMessage("On Python 3 '%s' % b'abc' produces \"b'abc'\", not 'abc'; use '%r' % b'abc' if this is desired behavior", codes.STR_BYTES_PY3)
FORMAT_STR_INVALID_NUMERIC_FLAG: Final = ErrorMessage('Numeric flags are only allowed for numeric types', codes.STRING_FORMATTING)
FORMAT_STR_REPLACEMENT_NOT_FOUND: Final = ErrorMessage('Cannot find replacement for positional format specifier {}', codes.STRING_FORMATTING)
FORMAT_STR_NAMED_REPLACEMENT_NOT_FOUND: Final = ErrorMessage('Cannot find replacement for named format specifier "{}"', codes.STRING_FORMATTING)
FORMAT_STR_PARTIAL_FIELD_NUMBERING: Final = ErrorMessage('Cannot combine automatic field numbering and manual field specification', codes.STRING_FORMATTING)
FORMAT_STR_SYNTAX_ERROR: Final = ErrorMessage('Syntax error in format specifier "{}"', codes.STRING_FORMATTING)
FORMAT_STR_INVALID_ACCESSOR_EXPR: Final = ErrorMessage('Only index and member expressions are allowed in format field accessors; got "{}"', codes.STRING_FORMATTING)
FORMAT_STR_INVALID_INDEX_ACCESSOR: Final = ErrorMessage('Invalid index expression in format field accessor "{}"', codes.STRING_FORMATTING)
FORMAT_STR_BYTES_ABOVE_PY35: Final = ErrorMessage('Bytes formatting is only supported in Python 3.5 and later', codes.STRING_FORMATTING)
FORMAT_STR_BYTES_DICT_KEYS_MUST_BE_BYTES: Final = ErrorMessage('Dictionary keys in bytes formatting must be bytes, not strings', codes.STRING_FORMATTING)
FORMAT_STR_BYTES_REQUIRED_PY3: Final = ErrorMessage("On Python 3 b'%s' requires bytes, not string", codes.STRING_FORMATTING)
FORMAT_STR_INVALID_BYTES_SPECIFIER_PY35: Final = ErrorMessage('Format character "b" is only supported in Python 3.5 and later', codes.STRING_FORMATTING)
FORMAT_STR_INVALID_BYTES_SPECIFIER: Final = ErrorMessage('Format character "b" is only supported on bytes patterns', codes.STRING_FORMATTING)
FORMAT_STR_ASCII_SPECIFIER_PY3: Final = ErrorMessage('Format character "a" is only supported in Python 3', codes.STRING_FORMATTING)
