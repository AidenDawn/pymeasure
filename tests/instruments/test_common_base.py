#
# This file is part of the PyMeasure package.
#
# Copyright (c) 2013-2022 PyMeasure Developers
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

import pytest

from pymeasure.units import ureg
from pymeasure.test import expected_protocol
from pymeasure.instruments.common_base import DynamicProperty, CommonBase
from pymeasure.adapters import FakeAdapter, ProtocolAdapter
from pymeasure.instruments.validators import strict_discrete_set, strict_range, truncated_range


class CommonBaseTesting(CommonBase):
    """Add read/write methods in order to use the ProtocolAdapter."""

    def __init__(self, parent, id=None, *args, **kwargs):
        super().__init__()
        self.parent = parent
        self.id = id
        self.args = args
        self.kwargs = kwargs

    def wait_for(self, query_delay=0):
        pass

    def write(self, command):
        self.parent.write(command)

    def read(self):
        return self.parent.read()


class GenericBase(CommonBaseTesting):
    #  Use truncated_range as this easily lets us test for the range boundaries
    fake_ctrl = CommonBase.control(
        "C{ch}:control?", "C{ch}:control %d", "docs",
        validator=truncated_range,
        values=(1, 10),
        dynamic=True,
    )
    fake_setting = CommonBase.setting(
        "C{ch}:setting %d", "docs",
        validator=truncated_range,
        values=(1, 10),
        dynamic=True,
    )
    fake_measurement = CommonBase.measurement(
        "C{ch}:measurement?", "docs",
        values={'X': 1, 'Y': 2, 'Z': 3},
        map_values=True,
        dynamic=True,
    )
    special_control = CommonBase.control(
        "SOUR{ch}:special?", "OUTP{ch}:special %s",
        """A special control with different channel specifiers for get and set.""",
        cast=str,
    )


@pytest.fixture()
def generic():
    return GenericBase()


class FakeBase(CommonBaseTesting):
    def __init__(self, *args, **kwargs):
        super().__init__(FakeAdapter())

    fake_ctrl = CommonBase.control(
        "", "%d", "docs",
        validator=truncated_range,
        values=(1, 10),
        dynamic=True,
    )
    fake_setting = CommonBase.setting(
        "%d", "docs",
        validator=truncated_range,
        values=(1, 10),
        dynamic=True,
    )
    fake_measurement = CommonBase.measurement(
        "", "docs",
        values={'X': 1, 'Y': 2, 'Z': 3},
        map_values=True,
        dynamic=True,
    )


@pytest.fixture()
def fake():
    return FakeBase()


class ExtendedBase(FakeBase):
    # Keep values unchanged, just derive another instrument, e.g. to add more properties
    fake_ctrl2 = CommonBase.control(
        "", "%d", "docs",
        validator=strict_range,
        values=(1, 10),
        dynamic=True,
    )

    fake_ctrl2_values = (5, 20)


class StrictExtendedBase(ExtendedBase):
    # Use strict instead of truncated range validator
    fake_ctrl_validator = strict_range
    fake_setting_validator = strict_range


class NewRangeBase(FakeBase):
    # Choose different properties' values, like you would for another device model
    fake_ctrl_values = (10, 20)
    fake_setting_values = (10, 20)
    fake_measurement_values = {'X': 4, 'Y': 5, 'Z': 6}


class Child(CommonBase):
    """A child, which accepts parent and id arguments."""

    def __init__(self, parent, id=None, *args, **kwargs):
        super().__init__()


class Parent(CommonBaseTesting):
    """A Base as a parent"""
    channels = CommonBase.ChannelCreator(GenericBase, ("A", "B", "C"))
    analog = CommonBase.ChannelCreator(GenericBase, [1, 2], prefix="an_", test=True)
    function = CommonBase.ChannelCreator(Child, prefix=None)


# Test dynamic properties
def test_dynamic_property_fget_unset():
    d = DynamicProperty()
    with pytest.raises(AttributeError, match="Unreadable attribute"):
        d.__get__(5)


def test_dynamic_property_fset_unset():
    d = DynamicProperty()
    with pytest.raises(AttributeError, match="set attribute"):
        d.__set__(5, 7)


# Test CommonBase Children management
class TestInitWithChildren:
    @pytest.fixture()
    def parent(self):
        return Parent(ProtocolAdapter())

    def test_channels(self, parent):
        assert len(parent.channels) == 3
        assert isinstance(parent.ch_A, GenericBase)

    def test_analog(self, parent):
        assert len(parent.analog) == 2
        assert parent.an_1 == parent.analog[1]
        assert isinstance(parent.analog[1], GenericBase)

    def test_function(self, parent):
        assert isinstance(parent.function, Child)

    def test_removal_of_protected_children_fails(self, parent):
        with pytest.raises(TypeError, match="cannot remove channels defined at class"):
            parent.remove_child(parent.ch_A)

    def test_removal_of_protected_single_children_fails(self, parent):
        with pytest.raises(TypeError, match="cannot remove channels defined at class"):
            parent.remove_child(parent.function)

    def test_channel_creation_works_more_than_once(self):
        """A zipper object works just once, ensure that a class may be used more often."""
        p1 = Parent(ProtocolAdapter())  # first instance of that class
        assert isinstance(p1.analog[1], GenericBase)  # verify that it worked once
        p2 = Parent(ProtocolAdapter())  # second instance of that class
        assert isinstance(p2.analog[1], GenericBase)  # verify that it worked a second time


class TestAddChild:
    """Test the `add_child` method"""
    @pytest.fixture()
    def parent(self):
        parent = CommonBaseTesting(ProtocolAdapter())
        parent.add_child(GenericBase, "A", test=5)
        parent.add_child(GenericBase, "B")
        parent.add_child(GenericBase, prefix=None, collection="function")
        return parent

    def test_correct_class(self, parent):
        assert isinstance(parent.ch_A, GenericBase)

    def test_arguments(self, parent):
        assert parent.channels["A"].id == "A"
        assert parent.channels["A"].kwargs == {'test': 5}

    def test_attribute_access(self, parent):
        assert parent.ch_B == parent.channels["B"]

    def test_len(self, parent):
        assert len(parent.channels) == 2

    def test_attributes(self, parent):
        assert parent.ch_A._name == "ch_A"
        assert parent.ch_B._collection == "channels"

    def test_overwriting_list_raises_error(self, parent):
        """A single channel is only allowed, if there is no list of that name."""
        with pytest.raises(ValueError, match="already exists"):
            parent.add_child(GenericBase, prefix=None)

    def test_single_channel(self, parent):
        """Test, that id=None creates a single channel."""
        assert isinstance(parent.function, GenericBase)
        assert parent.function._name == "function"

    def test_evaluating_false_id_creates_channels(self, parent):
        """Test that an id evaluating false (e.g. 0) creates a channels list."""
        parent.add_child(GenericBase, 0, collection="special")
        assert isinstance(parent.special, dict)


class TestRemoveChild:
    @pytest.fixture()
    def parent_without_children(self):
        parent = CommonBaseTesting(ProtocolAdapter())
        parent.add_child(GenericBase, "A")
        parent.add_child(GenericBase, "B")
        parent.add_child(GenericBase, prefix=None, collection="function")
        parent.remove_child(parent.ch_A)
        parent.remove_child(parent.channels["B"])
        parent.remove_child(parent.function)
        return parent

    def test_remove_child_leaves_channels_empty(self, parent_without_children):
        assert parent_without_children.channels == {}

    def test_remove_child_clears_attributes(self, parent_without_children):
        assert getattr(parent_without_children, "ch_A", None) is None
        assert getattr(parent_without_children, "ch_B", None) is None
        assert getattr(parent_without_children, "function", None) is None


class TestInheritanceWithChildren:
    class InstrumentSubclass(Parent):
        """Override one channel group, inherit other groups."""
        function = CommonBase.ChannelCreator(GenericBase, "overridden", prefix=None)

    @pytest.fixture()
    def parent(self):
        return self.InstrumentSubclass(ProtocolAdapter())

    def test_inherited_children_are_present(self, parent):
        assert isinstance(parent.ch_A, GenericBase)

    def test_ChannelCreator_is_replaced_by_channel_collection(self, parent):
        assert not isinstance(parent.channels, CommonBase.ChannelCreator)

    def test_overridden_child_is_present(self, parent):
        assert parent.function.id == "overridden"


# Test ChannelCreator
@pytest.mark.parametrize("args, pairs, kwargs", (
    ((Child, ["A", "B"]), [(Child, "A"), (Child, "B")], {'prefix': "ch_"}),
    (((Child, GenericBase, Child), (1, 2, 3)),
     [(Child, 1), (GenericBase, 2), (Child, 3)], {'prefix': "ch_"}),
    ((Child, "mm", None), [(Child, "mm")], {'prefix': None}),
    ((Child, None, None), [(Child, None)], {'prefix': None}),
))
def test_ChannelCreator(args, pairs, kwargs):
    """Test whether the channel creator receives the right arguments."""
    d = CommonBase.ChannelCreator(*args)
    i = 0
    for pair in d.pairs:
        assert pair == pairs[i]
        i += 1
    assert d.kwargs == kwargs


def test_ChannelCreator_different_list_lengths():
    with pytest.raises(AssertionError, match="Lengths"):
        CommonBase.ChannelCreator(("A", "B", "C"), (Child,) * 2)


def test_ChannelCreator_invalid_input():
    with pytest.raises(ValueError, match="Invalid"):
        CommonBase.ChannelCreator("A", {})


# Test CommonBase communication
def test_ask_writes_and_reads():
    with expected_protocol(CommonBaseTesting, [("Sent", "Received")]) as inst:
        assert inst.ask("Sent") == "Received"


@pytest.mark.parametrize("value, kwargs, result",
                         (("5,6,7", {}, [5, 6, 7]),
                          ("5.6.7", {'separator': '.'}, [5, 6, 7]),
                          ("5,6,7", {'cast': str}, ['5', '6', '7']),
                          ("X,Y,Z", {}, ['X', 'Y', 'Z']),
                          ("X,Y,Z", {'cast': str}, ['X', 'Y', 'Z']),
                          ("X.Y.Z", {'separator': '.'}, ['X', 'Y', 'Z']),
                          ("0,5,7.1", {'cast': bool}, [False, True, True]),
                          ("x5x", {'preprocess_reply': lambda v: v.strip("x")}, [5])
                          ))
def test_values(value, kwargs, result):
    cb = CommonBaseTesting(FakeAdapter(), "test")
    assert cb.values(value, **kwargs) == result


def test_binary_values(fake):
    fake.read_binary_values = fake.read
    assert fake.binary_values("123") == "123"


# Test CommonBase property creators
@pytest.mark.parametrize("dynamic", [False, True])
def test_control_doc(dynamic):
    doc = """ X property """

    class Fake(CommonBaseTesting):
        x = CommonBase.control(
            "", "%d", doc,
            dynamic=dynamic
        )

    expected_doc = doc + "(dynamic)" if dynamic else doc
    assert Fake.x.__doc__ == expected_doc


def test_control_check_errors_get(fake):
    fake.fake_ctrl_check_get_errors = True

    def checking():
        fake.error = True
    fake.check_errors = checking
    fake.fake_ctrl
    assert fake.error is True


def test_control_check_errors_set(fake):
    fake.fake_ctrl_check_set_errors = True

    def checking():
        fake.error = True
    fake.check_errors = checking
    fake.fake_ctrl = 7
    assert fake.error is True


@pytest.mark.parametrize("dynamic", [False, True])
def test_control_validator(dynamic):
    class Fake(FakeBase):
        x = CommonBase.control(
            "", "%d", "",
            validator=strict_discrete_set,
            values=range(10),
            dynamic=dynamic
        )

    fake = Fake()
    fake.x = 5
    assert fake.read() == '5'
    fake.x = 5
    assert fake.x == 5
    with pytest.raises(ValueError):
        fake.x = 20


@pytest.mark.parametrize("dynamic", [False, True])
def test_control_validator_map(dynamic):
    class Fake(FakeBase):
        x = CommonBase.control(
            "", "%d", "",
            validator=strict_discrete_set,
            values=[4, 5, 6, 7],
            map_values=True,
            dynamic=dynamic
        )

    fake = Fake()
    fake.x = 5
    assert fake.read() == '1'
    fake.x = 5
    assert fake.x == 5
    with pytest.raises(ValueError):
        fake.x = 20


@pytest.mark.parametrize("dynamic", [False, True])
def test_control_dict_map(dynamic):
    class Fake(FakeBase):
        x = CommonBase.control(
            "", "%d", "",
            validator=strict_discrete_set,
            values={5: 1, 10: 2, 20: 3},
            map_values=True,
            dynamic=dynamic
        )

    fake = Fake()
    fake.x = 5
    assert fake.read() == '1'
    fake.x = 5
    assert fake.x == 5
    fake.x = 20
    assert fake.read() == '3'


@pytest.mark.parametrize("dynamic", [False, True])
def test_control_dict_str_map(dynamic):
    class Fake(FakeBase):
        x = CommonBase.control(
            "", "%d", "",
            validator=strict_discrete_set,
            values={'X': 1, 'Y': 2, 'Z': 3},
            map_values=True,
            dynamic=dynamic,
        )

    fake = Fake()
    fake.x = 'X'
    assert fake.read() == '1'
    fake.x = 'Y'
    assert fake.x == 'Y'
    fake.x = 'Z'
    assert fake.read() == '3'


def test_value_not_in_map(fake):
    fake.parent._buffer = "123"
    with pytest.raises(KeyError, match="not found in mapped values"):
        fake.fake_measurement


def test_control_invalid_values_get():
    class Fake(FakeBase):
        x = CommonBase.control(
            "", "%d", "",
            values=b"abasdfe", map_values=True)
    with pytest.raises(ValueError, match="Values of type"):
        Fake().x


def test_control_invalid_values_set():
    class Fake(FakeBase):
        x = CommonBase.control(
            "", "%d", "",
            values=b"abasdfe", map_values=True)
    with pytest.raises(ValueError, match="Values of type"):
        Fake().x = 7


@pytest.mark.parametrize("dynamic", [False, True])
def test_control_process(dynamic):
    class Fake(FakeBase):
        x = CommonBase.control(
            "", "%d", "",
            validator=strict_range,
            values=[5e-3, 120e-3],
            get_process=lambda v: v * 1e-3,
            set_process=lambda v: v * 1e3,
            dynamic=dynamic,
        )

    fake = Fake()
    fake.x = 10e-3
    assert fake.read() == '10'
    fake.x = 30e-3
    assert fake.x == 30e-3


@pytest.mark.parametrize("dynamic", [False, True])
def test_control_get_process(dynamic):
    class Fake(FakeBase):
        x = CommonBase.control(
            "", "JUNK%d", "",
            validator=strict_range,
            values=[0, 10],
            get_process=lambda v: int(v.replace('JUNK', '')),
            dynamic=dynamic,
        )

    fake = Fake()
    fake.x = 5
    assert fake.read() == 'JUNK5'
    fake.x = 5
    assert fake.x == 5


@pytest.mark.parametrize("dynamic", [False, True])
def test_control_preprocess_reply_property(dynamic):
    # test setting preprocess_reply at property-level
    class Fake(FakeBase):
        x = CommonBase.control(
            "", "JUNK%d",
            "",
            preprocess_reply=lambda v: v.replace('JUNK', ''),
            dynamic=dynamic,
            cast=int,
        )

    fake = Fake()
    fake.x = 5
    assert fake.read() == 'JUNK5'
    # notice that read returns the full reply since preprocess_reply is only
    # called inside CommonBase.values()
    fake.x = 5
    assert fake.x == 5
    fake.x = 5
    assert type(fake.x) == int


@pytest.mark.parametrize("cast, expected", ((float, 5.5),
                                            (ureg.Quantity, ureg.Quantity(5.5)),
                                            (str, "5.5"),
                                            (lambda v: int(float(v)), 5)
                                            ))
def test_measurement_cast(cast, expected):
    class Fake(CommonBaseTesting):
        x = CommonBase.measurement(
            "x", "doc", cast=cast)
    with expected_protocol(Fake, [("x", "5.5")], name="test") as instr:
        assert instr.x == expected


def test_measurement_cast_int():
    class Fake(CommonBaseTesting):
        def __init__(self, adapter, **kwargs):
            super().__init__(adapter, "test", **kwargs)
        x = CommonBase.measurement(
            "x", "doc", cast=int)
    with expected_protocol(Fake, [("x", "5")]) as instr:
        y = instr.x
        assert y == 5
        assert type(y) is int


def test_measurement_unitful_property():
    class Fake(CommonBaseTesting):
        def __init__(self, adapter, **kwargs):
            super().__init__(adapter, "test", **kwargs)
        x = CommonBase.measurement(
            "x", "doc", get_process=lambda v: ureg.Quantity(v, ureg.m))
    with expected_protocol(Fake, [("x", "5.5")]) as instr:
        y = instr.x
        assert y.m_as(ureg.m) == 5.5


@pytest.mark.parametrize("dynamic", [False, True])
def test_measurement_dict_str_map(dynamic):
    class Fake(FakeBase):
        x = CommonBase.measurement(
            "", "",
            values={'X': 1, 'Y': 2, 'Z': 3},
            map_values=True,
            dynamic=dynamic,
        )

    fake = Fake()
    fake.write('1')
    assert fake.x == 'X'
    fake.write('2')
    assert fake.x == 'Y'
    fake.write('3')
    assert fake.x == 'Z'


def test_measurement_set(fake):
    with pytest.raises(LookupError, match="Property can not be set."):
        fake.fake_measurement = 7


def test_setting_get(fake):
    with pytest.raises(LookupError, match="Property can not be read."):
        fake.fake_setting


@pytest.mark.parametrize("dynamic", [False, True])
def test_setting_process(dynamic):
    class Fake(FakeBase):
        x = CommonBase.setting(
            "OUT %d", "",
            set_process=lambda v: int(bool(v)),
            dynamic=dynamic,
        )

    fake = Fake()
    fake.x = False
    assert fake.read() == 'OUT 0'
    fake.x = 2
    assert fake.read() == 'OUT 1'


@pytest.mark.parametrize("dynamic", [False, True])
def test_control_multivalue(dynamic):
    class Fake(FakeBase):
        x = CommonBase.control(
            "", "%d,%d", "",
            dynamic=dynamic,
        )

    fake = Fake()
    fake.x = (5, 6)
    assert fake.read() == '5,6'


@pytest.mark.parametrize(
    'set_command, given, expected, dynamic',
    [("%d", 5, 5, False),
     ("%d", 5, 5, True),
     ("%d, %d", (5, 6), [5, 6], False),  # input has to be a tuple, not a list
     ("%d, %d", (5, 6), [5, 6], True),  # input has to be a tuple, not a list
     ])
def test_FakeBase_control(set_command, given, expected, dynamic):
    """FakeBase's custom simple control needs to process values correctly.
    """
    class Fake(FakeBase):
        x = FakeBase.control(
            "", set_command, "",
            dynamic=dynamic,
        )

    fake = Fake()
    fake.x = given
    assert fake.x == expected


def test_dynamic_property_unchanged_by_inheritance():
    generic = FakeBase()
    extended = ExtendedBase()

    generic.fake_ctrl = 50
    assert generic.fake_ctrl == 10
    extended.fake_ctrl = 50
    assert extended.fake_ctrl == 10

    generic.fake_setting = 50
    assert generic.read() == '10'
    extended.fake_setting = 50
    assert extended.read() == '10'

    generic.write('1')
    assert generic.fake_measurement == 'X'
    extended.write('1')
    assert extended.fake_measurement == 'X'


def test_dynamic_property_strict_raises():
    # Tests also that dynamic properties can be changed at class level.
    strict = StrictExtendedBase()

    with pytest.raises(ValueError):
        strict.fake_ctrl = 50
    with pytest.raises(ValueError):
        strict.fake_setting = 50


def test_dynamic_property_values_update_in_subclass():
    newrange = NewRangeBase()

    newrange.fake_ctrl = 50
    assert newrange.fake_ctrl == 20

    newrange.fake_setting = 50
    assert newrange.read() == '20'

    newrange.write('4')
    assert newrange.fake_measurement == 'X'


def test_dynamic_property_values_update_in_instance(fake):
    fake.fake_ctrl_values = (0, 33)
    fake.fake_ctrl = 50
    assert fake.fake_ctrl == 33

    fake.fake_setting_values = (0, 33)
    fake.fake_setting = 50
    assert fake.read() == '33'

    fake.fake_measurement_values = {'X': 7}
    fake.write('7')
    assert fake.fake_measurement == 'X'


def test_dynamic_property_values_update_in_one_instance_leaves_other_unchanged():
    generic1 = FakeBase()
    generic2 = FakeBase()

    generic1.fake_ctrl_values = (0, 33)
    generic1.fake_ctrl = 50
    generic2.fake_ctrl = 50
    assert generic1.fake_ctrl == 33
    assert generic2.fake_ctrl == 10


def test_dynamic_property_reading_special_attributes_forbidden(fake):
    with pytest.raises(AttributeError):
        fake.fake_ctrl_validator


def test_dynamic_property_with_inheritance():
    inst = ExtendedBase()
    # Test for inherited attribute
    with pytest.raises(AttributeError):
        inst.fake_ctrl_validator
    # Test for new attribute
    with pytest.raises(AttributeError):
        inst.fake_ctrl2_validator


def test_dynamic_property_values_defined_at_superclass_level():
    """Test whether a dynamic property can be changed a superclass level"""
    inst = StrictExtendedBase()
    # Test whether the change of values from (1, 10) to (5, 20) succeeded:
    inst.fake_ctrl2 = 17  # should raise an error if change unsuccessful
    with pytest.raises(ValueError):
        inst.fake_ctrl2 = 2  # should not raise an error if change unsuccessful
