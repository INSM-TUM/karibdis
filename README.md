<h1>KARIBDIS<br>
<sub class="tagline" style="font-size: .6em;">Knowledge-Augmented Reasoning for Intelligent Business Decision and Intelligence Support</sub>
</h1>

<sub>[![CI](https://github.com/INSM-TUM/karibdis/actions/workflows/python-test.yml/badge.svg)](https://github.com/INSM-TUM/karibdis/actions/workflows/python-test.yml)</sub>

Karibdis is a proof-of-concept research prototype for a **Knowledge-graph-based Business Process Management System** to enable semantically explainable process execution support. 
It allows to import process knowledge from various sources, such as text, event logs, or existing ontologies and knowledge graphs. 
The imported knowledge is stored in an internal RDF-based **Process Knowledge Graph**, which the system uses for providing grounded explanations for decision support.

## Functionalities & Usage
The easiest way to familarize yourself with the functionality and usage of the prototype is to watch the [demonstration video](https://doi.org/10.6084/m9.figshare.30529892) or have a look at our research articles (see below).

Generally, the application is split into four views relating to different tasks on and next to the path from process knowledge sources to semantically explainable execution support, namely Knowledge Modeling, Decision Making, Task Execution, and Graph Exploration.


## Running the Application
### Prerequisites & Setup
This project requires Python. We recommend version 3.12, but support 3.10 and 3.11 as well. 
Further, git lfs is needed for cloning the example use case data. 
Lastly, for the textual knowledge importer, GPT is used. If you want to use this importer, please provide an `OPENAI_API_KEY` via the environment (e.g., through a `.env` file).

To set Karibdis up, first clone this repository and navigate into the project folder. If you want to use the example use case data, please also run `git lfs pull`.<br>
We strongly recommend to further set up and use a [virtual environment](https://docs.python.org/3/library/venv.html), e.g., with 
``` bash
python3 -m venv .venv
```

Then, please install the necessary Python libraries for running the system using the following command: 
``` bash
pip install -r requirements.txt 
```

You can now run Karibdis.


### Quick-start
To simply run Karibids as a web application, execute the following command from within the repository folder:
``` bash
voila karibdis.ipynb
```
This runs the application at localhost. It should open automatically in your browser, otherwise navigate to [localhost:8866](http://localhost:8866/) manually. 
After a short loading screen, the application will be visible and ready to use.


### Running inside Jupyter Environment
Alternatively, to enable, i.a., programmatic manipulation of the knowledge graph for research, Karibdis is also able to run inside a Jupyter environment. 
To do so, in a Jupyter cell, import the karibdis `JupyterApplication` class, and execute the `run` method. You can then access the application internals via the respective attributes of the application object:

``` Python
from karibdis.Application import JupyterApplication
app = JupyterApplication()
app.run()
pkg = app.system.pkg # Get process knowledge graph object
```



## Publications
As the prototype is a result of our research work, please consider our related publications for deeper background information. <br>

Detailed insight into the rationales and theory behind the prototype design can be found in the following preprint: <br>
&emsp;[*Knowledge Graphs as Key Technology for Semantically Explainable Business Process Execution Support*](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5865391)<br>
&emsp;Leon Bein and Luise Pufahl. SSRN Preprint, 2025.

Further related publications include:
- [*Knowledge Graphs: A Key Technology for Explainable Knowledge-Aware Process Automation?*](https://link.springer.com/chapter/10.1007/978-3-031-78666-2_2) 
<br>Leon Bein and Luise Pufahl.  Business Process Management Workshops BPM 2024. Springer Nature, 2025.
- [*Kraft – a Knowledge-graph-based Resource Allocation Framework*](https://link.springer.com/chapter/10.1007/978-3-032-02936-2_11)
<br>Leon Bein, Niels Martin, and Luise Pufahl. International Conference on Business Process Management 2025. Springer Nature, 2025.
