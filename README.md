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