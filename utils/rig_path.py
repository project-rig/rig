#!/usr/bin/env python

"""Print the path of the local Rig installation."""

if __name__=="__main__":  # pragma: no cover
    import rig
    import os.path
    print(os.path.dirname(rig.__file__))
