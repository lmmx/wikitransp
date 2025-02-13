```sh
conda create -n wikitransp
conda activate wikitransp
conda install -c rapidsai -c nvidia -c numba -c conda-forge cudf=21.08 python=3.8 cudatoolkit=11.2
pip install -e .
```
