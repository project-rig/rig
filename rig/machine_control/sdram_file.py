class SDRAMFile(object):
    def __init__(self, machine_controller, x, y,
                 start_address=0x60000000,
                 end_address=0x6fffffff):
        """Create a file-like view onto the SDRAM of a chip.

        Parameters
        ----------
        machine_controller : :py:class:`~rig.machine_control.MachineController`
            A communicator to handle transmitting and receiving packets from
            the SpiNNaker machine.
        x : int
            The x co-ordinate of the chip to represent the SDRAM of.
        y : int
            The y co-ordinate of the chip to represent the SDRAM of.
        start_address : int
            Starting address of the SDRAM.
        end_address : int
            End address of the SDRAM.
        """
        # Store parameters
        self._x = x
        self._y = y
        self._machine_controller = machine_controller
        self._start_address = start_address
        self._end_address = end_address

        # Current offset from start address
        self._offset = 0

    def read(self, n_bytes):
        """Read a number of bytes from the SDRAM.

        Parameters
        ----------
        n_bytes : int
            A number of bytes to read.

        Returns
        -------
        :py:class:`bytes`
            Data read from SpiNNaker as a bytestring.
        """
        # Determine how far to read, then read nothing beyond that point.
        if self.address + n_bytes > self._end_address:
            n_bytes = min(n_bytes, self._end_address - self.address)

            if n_bytes <= 0:
                return b''

        # Perform the read and increment the offset
        data = self._machine_controller.read(
            self._x, self._y, 0, self.address, n_bytes)
        self._offset += n_bytes
        return data

    def write(self, bytes):
        """Write data to the SDRAM.

        Parameters
        ----------
        bytes : :py:class:`bytes`
            Data to write to the SDRAM as a bytestring.

        Returns
        -------
        int
            Number of bytes written.
        """
        if self.address + len(bytes) > self._end_address:
            n_bytes = min(len(bytes), self._end_address - self.address)

            if n_bytes <= 0:
                return 0

            bytes = bytes[:n_bytes]

        # Perform the write and increment the offset
        self._machine_controller.write(
            self._x, self._y, 0, self.address, bytes)
        self._offset += len(bytes)
        return len(bytes)

    def tell(self):
        """Get the current offset in SDRAM.

        Returns
        -------
        int
            The current offset from SDRAM (starting at 0).
        """
        return self._offset

    @property
    def address(self):
        """Get the current address (indexed from 0x00000000)."""
        return self._offset + self._start_address

    def seek(self, n_bytes):
        """Seek to a new position in the file."""
        self._offset += n_bytes
