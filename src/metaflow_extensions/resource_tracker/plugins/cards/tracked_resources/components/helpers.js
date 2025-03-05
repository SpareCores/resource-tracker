function prettyTimestamp(unixTimestamp) {
    const date = new Date(unixTimestamp);
    const options = { 
        year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZoneName: 'short'
    };
    // YYYY-MM-DD HH:MM:SS GMT+1
    return date.toLocaleString('sv-SE', options);
};

// based on https://dygraphs.com/tests/legend-formatter.html + support for dashed lines
function legendFormatter(data) {
    if (data.x == null) {
        let html = '';
        data.series.forEach(function(series) {
            if (!series.isVisible) return;
            const seriesOptions = data.dygraph.getOption('series') || {};
            const seriesOpts = seriesOptions[series.label] || {};
            let dashStyle = '';
            if (seriesOpts.strokePattern && seriesOpts.strokePattern.length) {
                dashStyle = '<span style="display: inline-block; width: 30px; border-bottom: 3px dashed ' + series.color + '; margin-right: 5px;"></span>';
            } else {
                dashStyle = '<span style="display: inline-block; width: 30px; border-bottom: 3px solid ' + series.color + '; margin-right: 5px;"></span>';
            }
            html += dashStyle + ' ' + series.labelHTML + '<br/>';
        });
        return html;
    }

    var html = data.xHTML;
    data.series.forEach(function(series) {
        if (!series.isVisible) return;
        var labeledData = series.labelHTML + ': ' + series.yHTML;
        if (series.isHighlighted) {
            labeledData = '<b>' + labeledData + '</b>';
        }
        const seriesOptions = data.dygraph.getOption('series') || {};
        const seriesOpts = seriesOptions[series.label] || {};
        let dashStyle = '';
        if (seriesOpts.strokePattern && seriesOpts.strokePattern.length) {
            dashStyle = '<span style="display: inline-block; width: 30px; border-bottom: 3px dashed ' + series.color + '; margin-right: 5px;"></span>';
        } else {
            dashStyle = '<span style="display: inline-block; width: 30px; border-bottom: 3px solid ' + series.color + '; margin-right: 5px;"></span>';
        }
        html += '<br>' + dashStyle + ' ' + labeledData;
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
        axes : {
            x : {
                valueFormatter: Dygraph.dateString_,
                ticker: Dygraph.dateTicker,
                axisLabelFormatter: prettyTimestamp,
                axisLabelWidth: 70,
                axisTickSize: 5,
            }
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