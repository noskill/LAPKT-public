from . import pddl_types

class Predicate(object):
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments
    def parse(alist):
        name = alist[0]
        arguments = pddl_types.parse_typed_list(alist[1:], only_variables=True)
        return Predicate(name, arguments)
    parse = staticmethod(parse)

    def __hash__(self):
        return hash((self.name, tuple(hash(x.type) for x in self.arguments)))

    def __eq__(self, other):
        if not isinstance(other, Predicate):
            return False
        if len(other.arguments) != len(self.arguments):
           return False
        result = self.name == other.name
        for arg_self, arg_other in zip(self.arguments, other.arguments):
            result = result and (arg_self.type == arg_other.type)
        return result

    def __str__(self):
        return "%s(%s)" % (self.name, ", ".join(map(str, self.arguments)))

    def pddl(self):
        return "({0} {1})".format(self.name, ' '.join((x.pddl() for x in self.arguments)))

