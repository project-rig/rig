from rig.par import Machine, Cores, SDRAM, SRAM, Links


class TestMachine(object):
    def test_copied(self):
        """Test that arguments are coped"""
        width = 8
        height = 12

        chip_resources = {Cores: 1, SDRAM: 321, SRAM: 123}
        chip_resource_exceptions = {(0, 0): {SDRAM: 321, SRAM: 5}}

        dead_chips = set([(1, 1)])
        dead_links = set([(0, 0, Links.south_west),
                          (width-1, height-1, Links.north_east)])

        machine = Machine(width, height, chip_resources,
                          chip_resource_exceptions, dead_chips, dead_links)

        assert machine.width == width
        assert machine.height == height

        assert machine.chip_resources == chip_resources
        assert machine.chip_resources is not chip_resources
        assert machine.chip_resource_exceptions == chip_resource_exceptions
        assert machine.chip_resource_exceptions is not chip_resource_exceptions

        assert machine.dead_chips == dead_chips
        assert machine.dead_chips is not dead_chips
        assert machine.dead_links == dead_links
        assert machine.dead_links is not dead_links
