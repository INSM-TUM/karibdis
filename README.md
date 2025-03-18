# knowledge-graph-resource-allocation

## Prerequisites
This project uses Python 3.10. The version is necessary for compatibility with the simulator frame. 

First, clone this repository and navigate into the project folder.
This repository additionally utilizes the Business Process Optimization Competition 2023 simulation frame. Please download the respective zip file from the official [BPOC 2023 website](https://sites.google.com/view/bpo2023/competition) and unpack it as subfolder of the cloned project folder.

We strongly recommend the usage of a virtual environment, e.g., with
``` bash
python3.10 -m venv .venv
```

Then, please install the necessary Python libraries:
``` bash
pip install -r requirements.txt -r requirements_bpoc.txt
```


## Known Issues
- The simulator frame periodically returns a division by zero error (not caused by this project). In that case, just rerun the simulation
- The simulator might get stuck by only appropriating resources that cannot run the currently open tasks. In that case, just rerun the simulation


# External Files
This repository contains the `BPI Challenge 2017 - clean.csv` event log file retrieved from [the bpoc project](https://github.com/bpogroup/bpo-project/blob/a4aa6331166648b1920ef741e7a1eb65b8438904/bpo/resources/BPI%20Challenge%202017%20-%20clean.zip)