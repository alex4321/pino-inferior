import nbdev.test


def _wrap_parallel(old_parallel):
    def _func(*args, **kwargs):
        if "threadpool" not in kwargs:
            kwargs["threadpool"] = True
        return old_parallel(*args, **kwargs)

    return _func


if __name__ == "__main__":
    old_parallel = nbdev.test.parallel
    nbdev.test.parallel = _wrap_parallel(old_parallel)
    nbdev.test.nbdev_test(
        do_print=True,
        n_workers=1,
        timing=True,
    )
