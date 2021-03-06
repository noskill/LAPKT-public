from __future__ import print_function
import abc

from . import pddl_types
from . import f_expression


def parse_condition(alist):
    condition = parse_condition_aux(alist, False)
    # TODO: The next line doesn't appear to do anything good,
    # since uniquify_variables doesn't modify the condition in place.
    # Conditions in actions or axioms are uniquified elsewhere, but
    # it looks like goal conditions are never uniquified at all
    # (which would be a bug).
    condition.uniquify_variables({})
    return condition


def is_function_comparison(alist):
    tag = alist[0]
    if tag in (">","<",">=","<="):
        return True
    if not tag == "=":
        return False

    # tag is '='
    symbol = alist[1]
    if isinstance(symbol,list):
        if symbol[0] in ("+","/","*","-"):
            return True
        symbol = symbol[0]
    else:
        raise NotImplementedError(symbol)
    return False


def parse_condition_aux(alist, negated):
    """Parse a PDDL condition. The condition is translated into NNF on the fly."""
    tag = alist[0]
    if tag in ("and", "or", "not", "imply"):
        args = alist[1:]
        if tag == "imply":
            assert len(args) == 2
        if tag == "not":
            assert len(args) == 1
            return parse_condition_aux(args[0], not negated)
    elif tag in ("forall", "exists"):
        parameters = pddl_types.parse_typed_list(alist[1])
        args = alist[2:]
        assert len(args) == 1
    elif negated:
        return NegatedAtom(alist[0], alist[1:])
    elif is_function_comparison(alist):
        args = [f_expression.parse_expression(arg) for arg in alist[1:]]
        assert len(args) == 2, args
        if negated:
            return NegatedFunctionComparison(tag, args)
        else:
            return FunctionComparison(tag, args)
    else:
        return Atom(alist[0], alist[1:])
    if tag == "imply":
        parts = [parse_condition_aux(args[0], not negated),
                 parse_condition_aux(args[1], negated)]
        tag = "or"
    else:
        parts = [parse_condition_aux(part, negated) for part in args]

    if tag == "and" and not negated or tag == "or" and negated:
        return Conjunction(parts)
    elif tag == "or" and not negated or tag == "and" and negated:
        return Disjunction(parts)
    elif tag == "forall" and not negated or tag == "exists" and negated:
        return UniversalCondition(parameters, parts)
    elif tag == "exists" and not negated or tag == "forall" and negated:
        return ExistentialCondition(parameters, parts)


def parse_literal(alist):
    if alist[0] == "not":
        assert len(alist) == 2
        alist = alist[1]
        return NegatedAtom(alist[0], alist[1:])
    else:
        return Atom(alist[0], alist[1:])

# Conditions (of any type) are immutable, because they need to
# be hashed occasionally. Immutability also allows more efficient comparison
# based on a precomputed hash value.
#
# Careful: Most other classes (e.g. Effects, Axioms, Actions) are not!


class Condition(object):
    def __init__(self, parts):
        self.parts = tuple(parts)
        self.hash = hash((self.__class__, self.parts))

    def __hash__(self):
        return self.hash

    def __ne__(self, other):
        return not self == other

    def __lt__(self, other):
        return self.hash < other.hash

    def __le__(self, other):
        return self.hash <= other.hash

    def dump(self, indent="  "):
        print("%s%s" % (indent, self._dump()))
        for part in self.parts:
            part.dump(indent + "  ")

    def _dump(self):
        return self.__class__.__name__

    def _postorder_visit(self, method_name, *args):
        part_results = [part._postorder_visit(method_name, *args)
                        for part in self.parts]
        method = getattr(self, method_name, self._propagate)
        return method(part_results, *args)

    def _propagate(self, parts, *args):
        return self.change_parts(parts)

    def simplified(self):
        return self._postorder_visit("_simplified")

    def relaxed(self):
        return self._postorder_visit("_relaxed")

    def untyped(self):
        return self._postorder_visit("_untyped")

    def uniquify_variables(self, type_map, renamings={}):
        # Cannot used _postorder_visit because this requires preorder
        # for quantified effects.
        if not self.parts:
            return self
        else:
            return self.__class__([part.uniquify_variables(type_map, renamings)
                                   for part in self.parts])

    def to_untyped_strips(self):
        raise ValueError("Not a STRIPS condition: %s" % self.__class__.__name__)

    def instantiate(self, var_mapping, init_facts, fluent_facts, result):
        raise ValueError("Cannot instantiate condition: not normalized")

    def free_variables(self):
        result = set()
        for part in self.parts:
            result |= part.free_variables()
        return result

    def has_disjunction(self):
        for part in self.parts:
            if part.has_disjunction():
                return True
        return False

    def has_existential_part(self):
        for part in self.parts:
            if part.has_existential_part():
                return True
        return False

    def has_universal_part(self):
        for part in self.parts:
            if part.has_universal_part():
                return True
        return False

    def has_numeric_precondition(self):
        for part in self.parts:
            if part.has_numeric_precondition():
                return True
        return False

    @abc.abstractmethod
    def pddl(self):
        pass


class ConstantCondition(Condition):
    # Defining __eq__ blocks inheritance of __hash__, so must set it explicitly.
    __hash__ = Condition.__hash__
    parts = ()
    def __init__(self):
        self.hash = hash(self.__class__)
    def change_parts(self, parts):
        return self
    def __eq__(self, other):
        return self.__class__ is other.__class__


class Impossible(Exception):
    pass


class Falsity(ConstantCondition):
    def instantiate(self, var_mapping, init_facts, fluent_facts, result):
        raise Impossible()
    def negate(self):
        return Truth()


class Truth(ConstantCondition):
    def to_untyped_strips(self):
        return []
    def instantiate(self, var_mapping, init_facts, fluent_facts, result):
        pass
    def negate(self):
        return Falsity()


class JunctorCondition(Condition):
    # Defining __eq__ blocks inheritance of __hash__, so must set it explicitly.
    __hash__ = Condition.__hash__
    def __eq__(self, other):
        # Compare hash first for speed reasons.
        return (self.hash == other.hash and
                self.__class__ is other.__class__ and
                self.parts == other.parts)
    def change_parts(self, parts):
        return self.__class__(parts)


class Conjunction(JunctorCondition):
    def _simplified(self, parts):
        result_parts = []
        for part in parts:
            if isinstance(part, Conjunction):
                result_parts += part.parts
            elif isinstance(part, Falsity):
                return Falsity()
            elif not isinstance(part, Truth):
                result_parts.append(part)
        if not result_parts:
            return Truth()
        if len(result_parts) == 1:
            return result_parts[0]
        return Conjunction(result_parts)
    def to_untyped_strips(self):
        result = []
        for part in self.parts:
            result += part.to_untyped_strips()
        return result
    def instantiate(self, var_mapping, init_facts, fluent_facts, result):
        assert not result, "Condition not simplified"
        for part in self.parts:
            part.instantiate(var_mapping, init_facts, fluent_facts, result)
    def negate(self):
        return Disjunction([p.negate() for p in self.parts])
    def pddl(self):
        return '(and {0})'.format(' '.join(x.pddl() for x in self.parts))


class Disjunction(JunctorCondition):
    def _simplified(self, parts):
        result_parts = []
        for part in parts:
            if isinstance(part, Disjunction):
                result_parts += part.parts
            elif isinstance(part, Truth):
                return Truth()
            elif not isinstance(part, Falsity):
                result_parts.append(part)
        if not result_parts:
            return Falsity()
        if len(result_parts) == 1:
            return result_parts[0]
        return Disjunction(result_parts)
    def negate(self):
        return Conjunction([p.negate() for p in self.parts])
    def has_disjunction(self):
        return True

    def pddl(self):
        return '(or {0})'.format(' '.join(x.pddl() for x in self.parts))


class QuantifiedCondition(Condition):
    # Defining __eq__ blocks inheritance of __hash__, so must set it explicitly.
    __hash__ = Condition.__hash__
    def __init__(self, parameters, parts):
        self.parameters = tuple(parameters)
        self.parts = tuple(parts)
        self.hash = hash((self.__class__, self.parameters, self.parts))
    def __eq__(self, other):
        # Compare hash first for speed reasons.
        return (self.hash == other.hash and
                self.__class__ is other.__class__ and
                self.parameters == other.parameters and
                self.parts == other.parts)
    def _dump(self, indent="  "):
        arglist = ", ".join(map(str, self.parameters))
        return "%s %s" % (self.__class__.__name__, arglist)
    def _simplified(self, parts):
        if isinstance(parts[0], ConstantCondition):
            return parts[0]
        else:
            return self._propagate(parts)

    def uniquify_variables(self, type_map, renamings={}):
        renamings = dict(renamings) # Create a copy.
        new_parameters = [par.uniquify_name(type_map, renamings)
                          for par in self.parameters]
        new_parts = (self.parts[0].uniquify_variables(type_map, renamings),)
        return self.__class__(new_parameters, new_parts)

    def free_variables(self):
        result = Condition.free_variables(self)
        for par in self.parameters:
            result.discard(par.name)
        return result
    def change_parts(self, parts):
        return self.__class__(self.parameters, parts)


class UniversalCondition(QuantifiedCondition):
    def _untyped(self, parts):
        type_literals = [NegatedAtom(par.type, [par.name]) for par in self.parameters]
        return UniversalCondition(self.parameters,
                                  [Disjunction(type_literals + parts)])
    def negate(self):
        return ExistentialCondition(self.parameters, [p.negate() for p in self.parts])
    def has_universal_part(self):
        return True


class ExistentialCondition(QuantifiedCondition):
    def _untyped(self, parts):
        type_literals = [Atom(par.type, [par.name]) for par in self.parameters]
        return ExistentialCondition(self.parameters,
                                    [Conjunction(type_literals + parts)])
    def negate(self):
        return UniversalCondition(self.parameters, [p.negate() for p in self.parts])
    def instantiate(self, var_mapping, init_facts, fluent_facts, result):
        assert not result, "Condition not simplified"
        self.parts[0].instantiate(var_mapping, init_facts, fluent_facts, result)
    def has_existential_part(self):
        return True


class Literal(Condition):
    # Defining __eq__ blocks inheritance of __hash__, so must set it explicitly.
    __hash__ = Condition.__hash__
    parts = []
    def __init__(self, predicate, args):
        self.predicate = predicate
        self.args = tuple(args)
        self.hash = hash((self.__class__, self.predicate, self.args))
    def __eq__(self, other):
        # Compare hash first for speed reasons.
        return (self.hash == hash(other) and
                self.__class__ is other.__class__ and
                self.predicate == other.predicate and
                self.args == other.args)
    def __ne__(self, other):
        return not self == other
    @property
    def key(self):
        return str(self.predicate), self.args
    def __lt__(self, other):
        return self.key < other.key
    def __le__(self, other):
        return self.key <= other.key
    def __str__(self):
        return "%s %s(%s)" % (self.__class__.__name__, self.predicate,
                              ", ".join(map(str, self.args)))
    def __repr__(self):
        return '<%s>' % self
    def _dump(self):
        return str(self)
    def text( self ) :
        if len(self.args) == 0 :
            return "%s"%self.predicate
        return "%s_%s"%(self.predicate,"_".join(map(str,self.args)))

    def change_parts(self, parts):
        return self
    def uniquify_variables(self, type_map, renamings={}):
        return self.rename_variables(renamings)
    def rename_variables(self, renamings):
        new_args = tuple(renamings.get(arg, arg) for arg in self.args)
        return self.__class__(self.predicate, new_args)
    def replace_argument(self, position, new_arg):
        new_args = list(self.args)
        new_args[position] = new_arg
        return self.__class__(self.predicate, new_args)
    def free_variables(self):
        return set(arg for arg in self.args if arg[0] == "?")


class Atom(Literal):
    negated = False
    def to_untyped_strips(self):
        return [self]
    def instantiate(self, var_mapping, init_facts, fluent_facts, result):
        args = [var_mapping.get(arg, arg) for arg in self.args]
        atom = Atom(self.predicate, args)
        if atom in fluent_facts:
            result.append(atom)
        elif atom not in init_facts:
            raise Impossible()
    def negate(self):
        return NegatedAtom(self.predicate, self.args)
    def positive(self):
        return self

    def has_numeric_precondition(self):
        return False

    def pddl(self):
        try:
            return "({0} {1})".format(self.predicate, ' '.join(x.name if isinstance(x, pddl_types.TypedObject) else x for x in self.args))
        except TypeError as e:
            import pdb;pdb.set_trace()


class NegatedAtom(Atom):
    negated = True
    def _relaxed(self, parts):
        return Truth()
    def instantiate(self, var_mapping, init_facts, fluent_facts, result):
        args = [var_mapping.get(arg, arg) for arg in self.args]
        atom = Atom(self.predicate, args)
        if atom in fluent_facts:
            result.append(NegatedAtom(self.predicate, args))
        elif atom in init_facts:
            raise Impossible()
    def negate(self):
        return Atom(self.predicate, self.args)
    positive = negate

    def pddl(self):
        return '(not {0})'.format(self.negate().pddl())


class NumericWrapper(Literal):
    negated = False
    def __init__(self, name, args, bound_expression):
        self.expression = bound_expression
        self.predicate = name
        self.args = tuple(args)
        self.hash = hash((self.__class__, self.negated, self.predicate, self.args))

    def instantiate(self, var_mapping, init_facts, fluent_facts, result):
        args = [var_mapping.get(arg, arg) for arg in self.args]
        tmp = []
        self.expression.instantiate(var_mapping, init_facts, fluent_facts, tmp)
        assert len(tmp) == 1
        result.append(self.__class__(self.predicate, args, tmp[0]))

    def to_atom(self):
        return Atom(self.predicate, self.args)

    def pddl(self):
        s = '({0})'
        if self.negated:
            s = '(not ({0}))'
        return s.format(self.predicate + ' ' + ' '.join(self.args))


class NegatedNumericWrapper(NumericWrapper):
    negated = True
    def __init__(self, name, args, bound_expression):
        super(NegatedNumericWrapper, self).__init__(name, args, bound_expression)


class FunctionComparison(Condition): # comparing numerical functions
    negated = False

    def _relaxed(self, parts):
        return Truth()

    def __init__(self, comparator, parts, compare_to_zero = False):
        self.comparator = comparator
        assert len(parts) == 2
        if compare_to_zero:
            self.parts = (f_expression.FunctionalExpression(parts), f_expression.NumericConstant(0))
        else:
            self.parts = tuple(parts)
        self.pddl()
        self.hash = hash((self.__class__, self.comparator, self.parts))

    def get_functions(self):
        result = set()
        for part in self.parts:
            if isinstance(part, f_expression.PrimitiveNumericExpression):
                result.add(part)
            elif isinstance(part, f_expression.FunctionalExpression):
                result = result.union(part.get_functions())
            elif isinstance(part, f_expression.NumericConstant):
                pass
            else:
                raise NotImplementedError
        return result

    def negate(self):
        return NegatedFunctionComparison(self.comparator, self.parts)

    def _dump(self, indent="  "):
        return "%s %s" % (self.__class__.__name__, self.comparator)

    def has_disjunction(self):
        return False

    def has_existential_part(self):
        return False

    def has_universal_part(self):
        return False

    def has_numeric_precondition(self):
        return True

    def _simplified(self, parts):
        """
        Brings numeric precondition function to normal form.
        Normal function is of form (f(state)) > 0 or (f(state) >= 0)
        :param parts: list of parts of FunctionComparison
        :return: normalized FunctionComparison
        """

        prim = f_expression.PrimitiveNumericExpression
        zero_num = f_expression.NumericConstant(0)
        table = dict()

        def is_zero(item):
            if isinstance(item, f_expression.NumericConstant):
                if item.value == 0:
                    return True
                return False
            return False

        def more_equal(operator, left, right):
            lz = is_zero(left)
            rz = is_zero(right)
            if lz and rz:
                if operator == '>':
                    return Falsity()
                return Truth()
            if lz:
                if operator == '>':  # 0 > f(a)
                    new_op = '>='
                    # result is (not (f(a) >= 0))
                else:  # 0 >= f(a)
                    new_op = '>'
                    # result is (not (f(a) > 0))
                return NegatedFunctionComparison(new_op, [right, left])
            if rz:
                # already in normal form
                return FunctionComparison(operator, [left, right])
            return FunctionComparison(operator, [prim('-', (left, right)), zero_num])

        def equality(op, left, right):
            return Conjunction([more_equal('>=', f_expression.PrimitiveNumericExpression('-', left, right), zero_num),
                               more_equal('>=', f_expression.PrimitiveNumericExpression('-', right, left), zero_num)])

        table.update({'>': more_equal,
                      '>=': more_equal,
                      '<': lambda op, left, right: more_equal('>', right, left),
                      '<=': lambda op, left, right: more_equal('>=', right, left),
                      '=': lambda op, left, right: equality(op, left, right)
                 })

        assert len(parts) == 2
        result = table.get(self.comparator)(self.comparator, parts[0], parts[1])
        return result

    def pddl(self):
        return "({0} {1})".format(self.comparator,
                                  ' '.join(x.pddl() for x in self.parts))

    def uniquify_variables(self, type_map, renamings={}):
        return self.__class__(self.comparator, [part.rename_variables(renamings)
                                                for part in self.parts])

    def change_parts(self, parts):
        return self.__class__(self.comparator,parts)

    def instantiate(self, var_mapping, init_facts, fluent_facts, result):
        tmp_res = []
        for part in self.parts:
            tmp_res.append(part.instantiate(var_mapping, init_facts))
        result.append(self.__class__(self.comparator, tmp_res))


class NegatedFunctionComparison(FunctionComparison):
    negated = True

    def negate(self):
        return FunctionComparison(self.comparator, self.parts)
    positive = negate

    def pddl(self):
        return '(not {0})'.format(self.negate().pddl())
