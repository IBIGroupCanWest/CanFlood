﻿# CanFlood
Flood Risk modelling toolbox for Canada

## Beta 0.4.2 Release

Here are the working tools:

>Build: Setup, Inventory (w/ vFunc library), Hazard Sampler (w/ %inundation, prep), Event Variables, Conditional Probabilities (w/ event relation), DTM Sampler, Validation

>Model: Setup, Risk (L1), Impacts (L2), Risk (L2), Risk (L3)

>Results: Setup, Join Geo, Risk Plot (Plot Total, Plot Stack, Plot Fail Split), Compare

We welcome/encourage any comments, bugs, or issues you have or find. Please create a GitHub 'issue' ticket (on the issue tab) to let us know about these things.

Happy flood risk modelling!

## Installation Instructions 


1) Ensure Qgis 3.10.12 LTR is installed and working on your system ([Qgis all releases download page](https://qgis.org/downloads/)) with all the required python packages [requirements](https://github.com/IBIGroupCanWest/CanFlood/tree/master/requirements). 

2) During development, it's best to install two additional plugins to help with running CanFlood.  These can be installed from QGIS's plugin repository (Plugins > Manage and Install > 'All' > Search for desired plugin > 'Install Plugin'); however, ensure experimental plugins are searchable (from the plugins dialog > Settings > 'Show also experimental plugins'). The first helper plugin is [First Aid](https://plugins.qgis.org/plugins/firstaid/), which provides additional support for viewing errors in other plugins (essential for communicating your crash reports back to the develpoment team).  The second plugin is called 'Processing', and may be installed by default. 

3) Download the latest CanFlood zip from the above [plugin_zips folder](https://github.com/IBIGroupCanWest/CanFlood/tree/master/plugin_zips) to your computer (click the latest .zip, click the 'download' button. DO NOT right click ... 'Save As').

4) If you're re-installing or upgrading, its safest to first uninstall CanFlood and restart QGIS.  

5) In QGIS, install CanFlood to your profile from the newly downloaded zip  (Plugins > Manage and Install... > Install from Zip > navigate to the .zip > Install Plugin).

6) In QGIS, Turn the plugin on (Plugins > Manage and Install ... > Installed > check 'CanFlood'). If a dependency error is thrown, see 'troubleshooting' below.  If successful, you should see the three CanFlood buttons on your toolbar.

7) We recommend implementing the QGIS DEBUG logger for more detailed readouts and CanFlood model debugging. See [this post](https://stackoverflow.com/a/61669864/9871683) for insturctions.

### tl;dr
download the latest zip from [here](https://github.com/IBIGroupCanWest/CanFlood/tree/master/plugin_zips) and install from zip in QGIS. 

### Troubleshooting Installation

As both QGIS and CanFlood are active open source projects, getting your installation configured can be challenging, especially if you lack admin privileges to your machine and have no pyqgis experience. Some installations of QGIS may not come pre-installed with all the required python packages and dependencies listed in the [requirements](https://github.com/IBIGroupCanWest/CanFlood/tree/master/requirements) file.  If you get a ModuleNotFound error, your QGIS install does not have the required packages. This can be easily remedied by a user with admin privileges and working pyqgis knowledge.  The following [solution](https://github.com/IBIGroupCanWest/CanFlood/issues/6#issuecomment-592091488) provides some guidance on installing third party python modules, but you'll likely need admin privilege. 


## Getting Started

To get started with CanFlood, we recommend reading the latest users manual from the [manuals folder](https://github.com/IBIGroupCanWest/CanFlood/tree/master/manual) and working through the tutorials.


## I'm getting Errors!
As CanFlood is an active open-sourced project, users will often encounter errors which can be frustrating.  To work through these errors, we recommend first checking to see if there is a similar issue on the above '[Issues](https://github.com/IBIGroupCanWest/CanFlood/issues)' tab.  If so, hopefully the thread will resolve the problem, if not, reply to the thread with more details on your problem and why the posted solution did not work.

If there is no issue ticket yet, follow the instructions [here](https://github.com/IBIGroupCanWest/CanFlood/issues/49).



## CanFlood needs more features!
We agree. Consider contacting a CanFlood developer to sponsor new content that suites your needs, or joining the development community. Whether you'd like to integrate CanFlood modelling with some existing local data bases, or integrate some other flood risk models into your analysis, or develop new output styles, the CanFlood project wants to hear from you. Please post a new issue [here](https://github.com/IBIGroupCanWest/CanFlood/issues/new) with an 'enhancement' label.
