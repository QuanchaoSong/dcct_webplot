import numpy as np
from scipy.optimize import curve_fit
from io import StringIO
import os
import operator
import math
from pyodide.http import open_url, pyfetch
import json
from js import Bokeh, console, JSON, window, alert
from bokeh import events
from bokeh.models import CustomJS, Div, ColumnDataSource, DataRange1d
from bokeh.embed import json_item
from bokeh.plotting import figure
from bokeh.resources import CDN
from bdio.bdio import BDIOReader

def my_plot(x, y, x_for_line=[], y_for_line=[], x_range=None, y_range=None, x_axis_label="Time[s]", y_axis_label="Data / particles", title="Graph"):
    """To plot a Bohek graph on the pyscript webpage, according to the the points data

    Args:
        x (list): should be a list, containing x-axis values of the points
        y (list): should be a list, containing y-axis values of the points
        x_for_line (list, optional): should be a list, containing x-axis values of the optimization line points. Defaults to [].
        y_for_line (list, optional): should be a list, containing y-axis values of the optimization line points. Defaults to [].
        x_range (list, optional): when `x_range` is a valid DataRange1d instance, the graph will display only x-axis data within the range. Defaults to None, which means to display all data on x-axis.
        y_range (list, optional): when `y_range` is a valid DataRange1d instance, the graph will display only y-axis data within the range. Defaults to None, which means to display all data on y-axis.
        x_axis_label (str, optional): the x-axis title. Defaults to "Time[s]".
        y_axis_label (str, optional): the y-axis title. Defaults to "Data / particles".
        title (str, optional): the title of the graph. Defaults to "Graph".
    """    
    p = figure(title=title, x_axis_label=x_axis_label, y_axis_label=y_axis_label)    
    p.circle(x, y, size=3, line_color="navy", fill_color="orange", fill_alpha=0.5)

    source_for_line = ColumnDataSource(data=dict(xl=x_for_line, yl=y_for_line))
    p.line("xl", "yl", source=source_for_line, line_width=3, line_color="tomato", line_alpha=0.5)

    p.js_on_event(events.RangesUpdate, callback_upadte_range(div=None, attributes=['x0','x1','y0','y1']))
    p.js_on_event(events.Reset, callback_reset())

    if (x_range is not None):
        p.x_range = x_range
    if (y_range is not None):
        p.y_range = y_range

    p_json = json.dumps(json_item(p, "graph-area"))
    graph_area = Element("graph-area").element
    graph_area.innerHTML = ""
    Bokeh.embed.embed_item(JSON.parse(p_json))


def callback_reset() -> CustomJS:
    """the callback function when the `Reset` toolbar of the Bokeh graph is clicked. 

    Returns:
        CustomJS: This returning result is actually a simple transfer of action. User clicks the `Reset` toolbar of the Bokeh graph, then the javascript codes will be evaluated, and the javascript codes simply call a Python function `fake_fit_curve`. So the click action is transfered from the `Reset` toolbar of the Bokeh graph to the `fake_fit_curve` Python function.
    """    
    return CustomJS(code=f'''
        console.log("Reset");
        const fake_button = document.getElementById("fake_button");
        fake_button.click();
    ''')


def callback_upadte_range(div: Div=None, attributes: list[str] = []) -> CustomJS:
    """the callback function when user moves the Bokeh graph or selects a certain area of the graph.

    Args:
        div (Div, optional): This parameter's existence is only because that the callback of `events.RangesUpdate` must have this parameter. We actually don't need to bother with this parameter, in our case. Defaults to None.
        attributes (list[str], optional): This parameter allows us to catch the updated range values. In our case, we pass `['x0','x1','y0','y1']` to it. Defaults to [].

    Returns:
        CustomJS: In the returning javascript codes, we simply transform all the should-be-catched attributes into numbers & push them into a list, and finnally update the `range_data` of the javascript global variable `window`.
    """    
    return CustomJS(args=dict(div=div), code=f'''
        const attrs = {attributes};
        const value_list = [];
        for (let i = 0; i < attrs.length; i++) {{
            const val = JSON.stringify(cb_obj[attrs[i]], function(key, val) {{
                return val;
            }})
            value_list.push(val);
        }}
        window.range_data = value_list;
    ''')


def fit_function(x, *p):
    """The fit function to be used for the function `curve_fit` of `scipy.optimize`. The fit function is to fit a exponential distribution.

    Args:
        x (float): The independent variable of the exponential distribution, i.e., the `x`.
        *p (list): A guessed initial pair of parameters for the fitting.

    Returns:
        float: The calcalated result used for `curve_fit` to update  parameters of the exponential distribution, i.e., the `y`.
    """    
    return p[0] * np.exp(-x / p[1]) + p[2]


def ensure_normal_range(x0, x1, y0, y1):
    """To make sure that `x0 <= x1`, `y0 <= y1`.

    Args:
        x0 (float): the x-value of left point
        x1 (float): the x-value of right point
        y0 (float): the y-value of lower point
        y1 (float): the y-value of upper point

    Returns:
        tuple: the ordered `x0, x1, y0, y1`, in tuple form.
    """    
    if (x0 > x1):
        tmp = x0
        x0 = x1
        x1 = tmp
    if (y0 > y1):
        tmp = y0
        y0 = y1
        y1 = tmp
    return (x0, x1, y0, y1)


def fake_fit_curve():
    """When user click the `Reset` toolbar of the Bokeh graph, this function will be called.
    This function operates as the followings:
    1. Assures that the graph is being displayed partially (i.e., user moves the graph or selected a certain area to see the data in detail).
    2. Collect all the points' data within the displaying window of the graph into lists `x_list_selection` & `y_list_selection`,
    3. Calculate an initially guessed point `p0`, pass it along with `fit_function`, `x_list_selection` & `y_list_selection` to `curve_fit`.
    4. Get the optimized result from `curve_fit`, i.e., the `tau` value, update the UI & draw a new Bokeh graph.
    """    
    if (hasattr(window, "range_data") == False):
        alert("Please select a certain range of data firstly")
        return
    if (hasattr(window, "old_range_data") == False):
        return
    old_value_list = window.old_range_data
    x0, x1, y0, y1 = float(old_value_list[0]), float(old_value_list[1]), float(old_value_list[2]), float(old_value_list[3])
    fx0, fx1, fy0, fy1 = xList[0], xList[-1], yList[0], yList[-1]
    if ((int(x0) == int(fx0)) and 
        (int(x1) == int(fx1)) and 
        (int(y0) == int(fy0)) and 
        (int(y1) == int(fy1))):
        return
    window.old_range_data = [fx0, fx1, fy0, fy1]
    x0, x1, y0, y1 = ensure_normal_range(x0, x1, y0, y1)
    x_list_selection, y_list_selection = [], []
    for i in range(len(xList)):
        x = xList[i]
        y = yList[i]
        if ((x < x0) or (x > x1)):
            continue
        if ((y < y0) or (y > y1)):
            continue
        x_list_selection.append(x)
        y_list_selection.append(y)
    if (len(x_list_selection) == 0):
        return
    x_list_selection = np.array(x_list_selection)
    y_list_selection = np.array(y_list_selection)

    p0 = [y_list_selection[0], x_list_selection[-1] - x_list_selection[0], ,min(y_list_selection)]
    popt, pconv, infodict, mesg, ier = curve_fit(fit_function, x_list_selection, y_list_selection, p0=p0, full_output=True)

    tau = popt[1]
    if (ier != 1):
        Element("hint-area").element.style.display = ""
    else:
        Element("hint-area").element.style.display = "none"
    Element("result-area-1").write("%.4f" % (tau))
    Element("result-area-2").write("%.4f" % (tau * math.log(2)))
    Element("result-area-3").write("%.4f" % (1.0 / tau))
    my_plot(xList, yList, x_for_line=x_list_selection, y_for_line=fit_function(x_list_selection, popt[0], popt[1], popt[2]))


def fit_curve():
    """When user click the `Fit Exponential` button on the webpage, this function will be called.
    This function operates as the followings:
    1. Assures that the `range_data` is different from last time's, i.e., user moves the graph a bit or selects a new area of data to see the data in detail.
    2. Collect all the points' data within the displaying window of the graph into lists `x_list_selection` & `y_list_selection`,
    3. Calculate an initially guessed point `p0`, pass it along with `fit_function`, `x_list_selection` & `y_list_selection` to `curve_fit`.
    4. Get the optimized result from `curve_fit`, i.e., the `tau` value, update the UI & draw a new Bokeh graph(with a specific range).
    """
    if (hasattr(window, "range_data") == False):
        alert("Please select a certain range of data firstly")
        return
    
    if (hasattr(window, "old_range_data") == False):
        window.old_range_data = None

    if (operator.eq(window.old_range_data, window.range_data) == True):
        return
    window.old_range_data = window.range_data

    value_list = window.range_data
    x0, x1, y0, y1 = float(value_list[0]), float(value_list[1]), float(value_list[2]), float(value_list[3])
    x0, x1, y0, y1 = ensure_normal_range(x0, x1, y0, y1)
    x_list_selection, y_list_selection = [], []
    for i in range(len(xList)):
        x = xList[i]
        y = yList[i]
        if ((x < x0) or (x > x1)):
            continue
        if ((y < y0) or (y > y1)):
            continue
        x_list_selection.append(x)
        y_list_selection.append(y)
    if (len(x_list_selection) == 0):
        alert("Please select a certain area containing some valid data")
        return
    x_list_selection = np.array(x_list_selection)
    y_list_selection = np.array(y_list_selection)
    p0 = [y_list_selection[0], x_list_selection[-1] - x_list_selection[0]]
    popt, pconv, infodict, mesg, ier = curve_fit(fit_function, x_list_selection, y_list_selection, p0=p0, full_output=True)

    tau = popt[1]
    if (ier != 1):
        Element("hint-area").element.style.display = ""
    else:
        Element("hint-area").element.style.display = "none"
    Element("result-area-1").write("%.4f" % (tau))
    Element("result-area-2").write("%.4f" % (tau * math.log(2)))
    Element("result-area-3").write("%.4f" % (1.0 / tau))
    my_plot(xList, yList, x_for_line=x_list_selection, y_for_line=fit_function(x_list_selection, popt[0], popt[1], popt[2]), x_range=DataRange1d(start=x0, end=x1), y_range=DataRange1d(start=y0, end=y1))


def handle_csv_stringio(sIO):
    """To get the x-axis and y-axis data points from a StringIO parameter, to draw the Bokeh graph

    Args:
        sIO (StringIO): we use the StringIO-type data here because `np.genfromtxt` requires it (it doesn't allow `String` type input)
    """    
    global xList, yList
    [xList, yList] = np.genfromtxt(sIO, delimiter="|", skip_header=1, unpack=True)
    my_plot(xList, yList)


def handle_csv_string(csvStr):
    """Same as `handle_csv_stringio`, only difference is that we firstly transform the input string into `StringIO`-type data

    Args:
        csvStr (str): the textt content of the csv file from the local disk or remote server
    """    
    sIO = StringIO(csvStr)
    handle_csv_stringio(sIO)   



def draw_graph_of_dummy_data():
    """When user clicks the `Draw Graph From Dummy` button, this function will be called.
    This function operates as the following:
    1. Generate data that corresponds to an exponential distribution, where `tau_sim` is a random number within the range [200, 500).
    2. Get `xList` & `yList` according the generated data
    3. Draw the Bokeh graph
    """    
    tau_sim = np.random.randint(200, 500)
    size = 10000
    bins = 200
    minY, maxY = 0, 1000
    data = np.random.exponential(tau_sim, size=size)
    global xList, yList
    yList = np.histogram(data, bins=bins, range=(minY, maxY))[0]
    xList = np.arange(minY, maxY, (maxY - minY)/bins)

    Element("dummy-data-params-area").write(str(tau_sim))

    my_plot(xList, yList)


def read_tdf_from_file(filename):
    """This function is to help us get the essential data like `xList`, `yList` for a Bokeh graph, from a data file of a special format: `.tdf`.

    Args:
        filename (str): The path of your `.tdf` file

    Returns:
        tuple: the essential data for us to draw the Bokeh graph: `xList, yList, x_label, y_label, title`
    """    
    stream = BDIOReader(filename)
    blocks = stream.get_directory()
    for block in blocks:
        if block.is_xycurve_block():
            stream.seek(block.get_pos())
            nb = stream.next_block()
            global xList, yList
            xList = nb.get_xvalues()
            yList = nb.get_yvalues()
            x_label = nb.get_xaxis_title()
            y_label = nb.get_yaxis_title()
            title = nb.title
    return xList, yList, x_label, y_label, title


async def draw_graph_of_local_file():
    """When user clicks the `Draw Graph From Local` button, this function will be called.
    This function operates as the following:
    1. Get the file path. If no file selected, directly return.
    2. Check the extension name of the selected file. If it is `.csv` file, transfer the text content to the `handle_csv_string` function, and a Bokeh graph will be showed.
    3. If the extension name of the selected file is not `.csv`, i.e., the `.tdf` file (because we only allow users to select a single either `.csv` or `.tdf` file),  write down the content buffer of the file into a local file `tdf_file.tdf` under the current working dir(`/home/pyodide`), then use `read_tdf_from_file` function to get the essential data like `xList` & `yList` from the `.tdf` file, finnaly draw the Bokeh graph.
    """    
    localInputElement = Element("data_local_file").element
    fileList = localInputElement.files.to_py()
    if (len(fileList) == 0):
        return
    _, entension_name = os.path.splitext(localInputElement.value)
    is_csv_file = (entension_name.lower() == ".csv")
    for f in fileList:
        if (is_csv_file):
            textData = await f.text()
            handle_csv_string(textData)
        else:
            arr_buffer = await f.arrayBuffer()
            obtained_bytes = arr_buffer.to_bytes()   
            with open("tdf_file.tdf", "wb") as tdf_file:
                tdf_file.write(obtained_bytes)
            global xList, yList
            xList, yList, x_label, y_label, title = read_tdf_from_file("tdf_file.tdf")
            my_plot(xList, yList, x_axis_label=x_label, y_axis_label=y_label, title=title)


async def draw_graph_of_url():
    """When user clicks the `Draw Graph From Local` button, this function will be called.
    This function operates as the following:
    1. Get the valid input url string
    2. Check the extension name of the url string. If it is `.csv`, then directly use `pyodide.http`'s `open_url` function to get the StringIO data, and pass it to the function `handle_csv_stringio` to show the Bokeh graph.
    3. If the extension name of the url string is `.tdf`, we use `pyodide.http`'s `pyfetch` function to get the content bytes of the remote file, write down the content buffer of the file into a local file `tdf_file.tdf` under the current working dir(`/home/pyodide`), then use `read_tdf_from_file` function to get the essential data like `xList` & `yList` from the `.tdf` file, finnaly draw the Bokeh graph.
    """    
    urlStr = Element('data_url').element.value
    if (len(urlStr) == 0):
        return
    _, entension_name = os.path.splitext(urlStr)
    if (entension_name.lower() == ".csv"):
        csvStringIO = open_url(urlStr)
        handle_csv_stringio(csvStringIO)
    elif (entension_name.lower() == ".tdf"):
        resp = await pyfetch(urlStr)
        if (resp.ok == False):
            print("Http error")
            return
        obtained_bytes = await resp.bytes()
        with open("tdf_file.tdf", "wb") as tdf_file:
            tdf_file.write(obtained_bytes)
        global xList, yList
        xList, yList, x_label, y_label, title = read_tdf_from_file("tdf_file.tdf")
        my_plot(xList, yList, x_axis_label=x_label, y_axis_label=y_label, title=title)
    else:
        alert("Please input a url string with either `.csv` or `.tdf` as the ending extension")
