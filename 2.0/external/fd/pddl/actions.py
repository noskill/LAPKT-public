from __future__ import print_function

import copy

from . import conditions
from . import effects
from . import pddl_types
from . import f_expression

class Action(object):
    def __init__(self, name, parameters, num_external_parameters,
                 precondition, a_effects, cost):
        assert 0 <= num_external_parameters <= len(parameters)
        self.name = name
        self.parameters = parameters
        # num_external_parameters denotes how many of the parameters
        # are "external", i.e., should be part of the grounded action
        # name. Usually all parameters are external, but "invisible"
        # parameters can be created when compiling away existential
        # quantifiers in conditions.
        self.num_external_parameters = num_external_parameters
        self.precondition = precondition
        self._effects = [x for x in a_effects if not isinstance(x, effects.NumericEffect)]
        self._num_effects = [x for x in a_effects if isinstance(x, effects.NumericEffect)]
        self.cost = cost
        self.uniquify_variables() # TODO: uniquify variables in cost?

    def __repr__(self):
        return "<Action %r at %#x>" % (self.name, id(self))

    def __hash__(self):
        return hash(self.pddl())

    def __ne__(self, other):
        return not self.__eq__(other)

    def __eq__(self, other):
        if self is other:
            return True
        if not isinstance(other, Action):
            return False
        return self.pddl() == other.pddl()

    def parse(alist):
        iterator = iter(alist)
        action_tag = next(iterator)
        assert action_tag == ":action"
        name = next(iterator)
        parameters_tag_opt = next(iterator)
        if parameters_tag_opt == ":parameters":
            parameters = pddl_types.parse_typed_list(next(iterator),
                                                     only_variables=True)
            precondition_tag_opt = next(iterator)
        else:
            parameters = []
            precondition_tag_opt = parameters_tag_opt
        if precondition_tag_opt == ":precondition":
            precondition = conditions.parse_condition(next(iterator))
            precondition = precondition.simplified()
            effect_tag = next(iterator)
        else:
            precondition = conditions.Conjunction([])
            effect_tag = precondition_tag_opt
        assert effect_tag == ":effect"
        effect_list = next(iterator)
        eff = []
        num_eff = []
        try:
            cost = effects.parse_effects(effect_list, eff, num_eff)
        except ValueError as e:
            raise SystemExit("Error in Action %s\nReason: %s." % (name, e))
        for rest in iterator:
            assert False, rest
        param_names = [x.name for x in parameters]
        for prec in precondition.parts:
            if isinstance(prec, conditions.Atom):
                args = prec.args
                assert all(x in param_names for  x in args if x.startswith('?'))
        for effect in eff:
            assert all(x in param_names for x in effect.literal.args if x.startswith('?'))
        return Action(name, parameters, len(parameters),
                      precondition, eff + num_eff, cost)
    parse = staticmethod(parse)
    def dump(self):
        print("%s(%s)" % (self.name, ", ".join(map(str, self.parameters))))
        print("Precondition:")
        self.precondition.dump()
        print("Effects:")
        for eff in self.effects:
            eff.dump()
        print("Cost:")
        if(self.cost):
            self.cost.dump()
        else:
            print("  None")
    def uniquify_variables(self):
        self.type_map = dict([(par.name, par.type) for par in self.parameters])
        self.precondition = self.precondition.uniquify_variables(self.type_map)
        for effect in self.effects:
            effect.uniquify_variables(self.type_map)
    def relaxed(self):
        new_effects = []
        for eff in self.effects:
            relaxed_eff = eff.relaxed()
            if relaxed_eff:
                new_effects.append(relaxed_eff)
        return Action(self.name, self.parameters, self.num_external_parameters,
                      self.precondition.relaxed().simplified(),
                      new_effects, cost=self.cost)
    def untyped(self):
        # We do not actually remove the types from the parameter lists,
        # just additionally incorporate them into the conditions.
        # Maybe not very nice.
        result = copy.copy(self)
        parameter_atoms = [par.to_untyped_strips() for par in self.parameters]
        new_precondition = self.precondition.untyped()
        result.precondition = conditions.Conjunction(parameter_atoms + [new_precondition])
        result.effects = [eff.untyped() for eff in self.effects]
        return result

    def instantiate(self, var_mapping, init_facts, fluent_facts, objects_by_type):
        """Return a PropositionalAction which corresponds to the instantiation of
        this action with the arguments in var_mapping. Only fluent parts of the
        conditions (those in fluent_facts) are included. init_facts are evaluated
        whilte instantiating.
        Precondition and effect conditions must be normalized for this to work.
        Returns None if var_mapping does not correspond to a valid instantiation
        (because it has impossible preconditions or an empty effect list.)"""

        arg_list = [var_mapping[par.name]
                    for par in self.parameters[:self.num_external_parameters]]
        name = "(%s %s)" % (self.name, " ".join(arg_list))

        precondition = []
        try:
            self.precondition.instantiate(var_mapping, init_facts,
                                          fluent_facts, precondition)
        except conditions.Impossible:
            return None
        t_effects = []
        for eff in self.effects:
            eff.instantiate(var_mapping, init_facts, fluent_facts,
                            objects_by_type, t_effects)
        numeric_effects = []
        for eff in self.numeric_effects():
            try:
                eff.instantiate(var_mapping, init_facts, fluent_facts,
                                objects_by_type, numeric_effects)
            except conditions.Impossible:
                return None
        if t_effects or numeric_effects:
            if self.cost is None:
                cost = 0
            else:
                try:
                    t_cost = self.cost.instantiate(var_mapping, init_facts)
                    if isinstance(t_cost.expression, f_expression.NumericConstant):
                        cost = int(t_cost.expression.value)
                    else:
                        cost = int(t_cost.expression.initial_value)
                except conditions.Impossible:
                    return None
            return PropositionalAction(name, precondition, t_effects, numeric_effects, cost)
        else:
            return None

    def pddl(self):
        cost = ''
        if self.cost is not None:
            cost = self.cost.pddl()
        return "(:action {0} \
                :parameters ({1}) \
                :precondition {2} \
                :effect (and {3}))".format(self.name,
                                     ' '.join(param.pddl() for param in self.parameters),
                                     self.precondition.pddl(),
                                     ' '.join(x.pddl() for x in (self._effects + self._num_effects)) + cost)

    @property
    def effects(self):
        return self._effects

    @effects.setter
    def effects(self, value):
        self._effects = [x for x in value if not isinstance(x, effects.NumericEffect)]
        self._num_effects = [x for x in value if isinstance(x, effects.NumericEffect)]

    def numeric_effects(self):
        return self._num_effects


    def pddl(self):
        cost = ''
        if self.cost is not None:
             cost = self.cost.pddl()
        return "(:action {0} \
                :parameters ({1}) \
                :precondition {2} \
                :effect (and {3}))".format(self.name,
                                     ' '.join(param.pddl() for param in self.parameters),
                                     self.precondition.pddl(),
                                     ' '.join(x.pddl() for x  in self.effects) + cost)

class PropositionalAction:
    def __init__(self, name, precondition, a_effects, numeric_effects, cost):
        self.name = name
        self.precondition = precondition
        self.add_effects = []
        self.del_effects = []
        self.numeric_effects = numeric_effects
        for condition, effect in a_effects:
            if not effect.negated:
                self.add_effects.append((condition, effect))
        # Warning: This is O(N^2), could be turned into O(N).
        # But that might actually harm performance, since there are
        # usually few effects.
        # TODO: Measure this in critical domains, then use sets if acceptable.
        for condition, effect in a_effects:
            if effect.negated and (condition, effect.negate()) not in self.add_effects:
                self.del_effects.append((condition, effect.negate()))
        self.cost = cost

    def __repr__(self):
        return "<PropositionalAction %r at %#x>" % (self.name, id(self))
    def dump(self):
        print(self.name)
        for fact in self.precondition:
            print("PRE: %s" % fact)
        for cond, fact in self.add_effects:
            print("ADD: %s -> %s" % (", ".join(map(str, cond)), fact))
        for cond, fact in self.del_effects:
            print("DEL: %s -> %s" % (", ".join(map(str, cond)), fact))
        print("cost:", self.cost)
