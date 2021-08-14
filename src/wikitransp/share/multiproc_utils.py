from __future__ import annotations

import multiprocessing as mp
from multiprocessing import Process, Pool
from more_itertools import chunked
from tqdm import tqdm
from functools import partial


__all__ = ["batch_multiprocess", "batch_multiprocess_with_return"]

def run_and_update(func, pbar):
    func()
    pbar.update()

def append_and_update(result, results_list, pbar):
    results_list.append(result)
    pbar.update()

def batch_multiprocess(
    function_list, n_cores=mp.cpu_count(), show_progress=False, tqdm_desc=None
):
    """
    Run a list of functions on ``n_cores`` (default: all CPU cores),
    with the option to show a progress bar using tqdm (default: shown).
    """
    # MAY HAVE BROKEN THIS
    print("MAY HAVE BROKEN THIS")
    iterator = [*chunked(function_list, n_cores)]
    if show_progress:
        pbar = tqdm(desc=tqdm_desc, total=len(function_list))
    for func_batch in iterator:
        procs = []
        for f in func_batch:
            if show_progress:
                f_tqdm = partial(run_and_update, func=f, pbar=pbar)
            target = f_tqdm if show_progress else f
            procs.append(Process(target=target))
        for p in procs:
            p.start()
        for p in procs:
            p.join()


def batch_multiprocess_with_return(
    function_list,
    pool_results=None,
    n_cores=mp.cpu_count(),
    show_progress=False,
    tqdm_desc=None,
):
    """
    Run a list of functions on ``n_cores`` (default: all CPU cores),
    with the option to show a progress bar using tqdm (default: shown).
    """
    iterator = [*chunked(function_list, n_cores)]
    pool_results = pool_results if pool_results else []
    pool = Pool(processes=n_cores)
    if show_progress:
        pbar = tqdm(total=len(function_list), desc=tqdm_desc)
    for func_batch in iterator:
        procs = []
        for f in func_batch:
            if show_progress:
                tqdm_cb = partial(append_and_update, results_list=pool_results, pbar=pbar)
            callback = tqdm_cb if show_progress else pool_results.append
            pool.apply_async(func=f, callback=tqdm_cb)
    pool.close()
    pool.join()
    return pool_results
