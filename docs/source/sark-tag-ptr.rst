.. _sark-tag-ptr:

``sark_tag_ptr`` implementation for SARK 1.3x
=============================================

The ``sark_tag_ptr`` function will be introduced in SARK 1.40 after being
erroneously omitted from SARK 1.3x. As an interim measure, users may simply
copy the function from below into their own project.

.. code-block:: c

    // Get a pointer to a tagged allocation. If the "app_id" parameter is zero
    // uses the core's app_id.
    void *sark_tag_ptr (uint tag, uint app_id)
    {
      if (app_id == 0)
        app_id = sark_vec->app_id;
      
      return (void *) sv->alloc_tag[(app_id << 8) + tag];
    }
