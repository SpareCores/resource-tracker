function prettyTimestamp(unixTimestamp) {
    const date = new Date(unixTimestamp);
    const options = {
        year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZoneName: 'short'
    };
    // YYYY-MM-DD HH:MM:SS GMT+1
    return date.toLocaleString('sv-SE', options);
};


/**
 * Formats the legend for a Dygraph chart based on https://dygraphs.com/tests/legend-formatter.html,
 * with added support for dashed lines and merging series with same color into single line.
 * @param {Object} data - The data object passed by Dygraph containing series information
 * @returns {string} HTML string for the formatted legend
 */
function legendFormatter(data) {
    // initial legend without any point selected
    if (data.x == null) {
        let html = '';
        const colorGroups = {};
        data.series.forEach(function(series) {
            if (!series.isVisible) return;
            if (!colorGroups[series.color]) {
                colorGroups[series.color] = [];
            }
            colorGroups[series.color].push(series);
        });
        Object.keys(colorGroups).forEach(function(color) {
            html += '<br>';
            colorGroups[color].forEach(function(series, index) {
                const seriesOptions = data.dygraph.getOption('series') || {};
                const seriesOpts = seriesOptions[series.label] || {};
                let dashStyle = '';
                if (seriesOpts.strokePattern && seriesOpts.strokePattern.length) {
                    dashStyle = '<span style="display: inline-block; width: 30px; height: 1em; vertical-align: middle; position: relative;"><span style="position: absolute; top: 50%; transform: translateY(-50%); width: 100%; border-bottom: 3px dashed ' + color + ';"></span></span>';
                } else {
                    dashStyle = '<span style="display: inline-block; width: 30px; height: 1em; vertical-align: middle; position: relative;"><span style="position: absolute; top: 50%; transform: translateY(-50%); width: 100%; border-bottom: 3px solid ' + color + ';"></span></span>';
                }
                html += dashStyle + ' <span style="vertical-align: middle;">' + series.labelHTML + '</span>';
                if (index < colorGroups[color].length - 1) {
                    html += '&nbsp;&nbsp;&nbsp;&nbsp;';
                }
            });
        });
        if (html.startsWith('<br>')) {
            html = html.substring(4);
        }
        return html;
    }

    var html = data.xHTML;
    const colorGroups = {};
    data.series.forEach(function(series) {
        if (!series.isVisible) return;
        if (!colorGroups[series.color]) {
            colorGroups[series.color] = [];
        }
        colorGroups[series.color].push(series);
    });
    Object.keys(colorGroups).forEach(function(color) {
        html += '<br>';
        colorGroups[color].forEach(function(series, index) {
            const seriesOptions = data.dygraph.getOption('series') || {};
            const seriesOpts = seriesOptions[series.label] || {};
            let dashStyle = '';
            if (seriesOpts.strokePattern && seriesOpts.strokePattern.length) {
                dashStyle = '<span style="display: inline-block; width: 30px; height: 1em; vertical-align: middle; position: relative;"><span style="position: absolute; top: 50%; transform: translateY(-50%); width: 100%; border-bottom: 3px dashed ' + color + ';"></span></span>';
            } else {
                dashStyle = '<span style="display: inline-block; width: 30px; height: 1em; vertical-align: middle; position: relative;"><span style="position: absolute; top: 50%; transform: translateY(-50%); width: 100%; border-bottom: 3px solid ' + color + ';"></span></span>';
            }
            var labeledData = series.labelHTML + ': ' + series.yHTML;
            if (series.isHighlighted) {
                labeledData = '<b>' + labeledData + '</b>';
            }
            html += dashStyle + ' <span style="vertical-align: middle;">' + labeledData + '</span>';
            if (index < colorGroups[color].length - 1) {
                html += '&nbsp;&nbsp;&nbsp;&nbsp;';
            }
        });
    });
    return html;
};

/**
 * Creates a Dygraph chart with predefined styling and configuration
 * @param {string} divId - The ID of the div element where the graph will be rendered
 * @param {string} csvData - CSV formatted data to populate the graph
 * @param {string} labelsDivId - The ID of the div element where the legend labels will be displayed
 * @param {Object} additionalOptions - Optional additional configuration options to merge with defaults
 * @returns {Dygraph} The configured Dygraph instance
 */
function createGraph(divId, csvData, labelsDivId, additionalOptions = {}) {
    const options = {
        labelsDiv: labelsDivId,
        animatedZooms: true,
        highlightSeriesBackgroundAlpha: 1,
        valueRange: [0, null],
        axes : {
            x : {
                valueFormatter: Dygraph.dateString_,
                ticker: Dygraph.dateTicker,
                axisLabelFormatter: prettyTimestamp,
                axisLabelWidth: 70,
                axisTickSize: 5,
            },
        },
        showRoller: true,
        axisLineColor: '#082F49',
        gridLineColor: '#fff',
        gridLineWidth: 0.2,
        colors: ['#34D399', '#38BDF8'],
        strokeWidth: 2,
        legend: 'always',
        legendFormatter: legendFormatter,
        highlightSeriesOpts: { strokeWidth: 3 },
        highlightCircleSize: 5,
        plugins: [
            new Dygraph.Plugins.Crosshair({direction: "vertical"})
        ],
        ...additionalOptions
    };

    return new Dygraph(
        document.getElementById(divId),
        csvData,
        options
    );
};