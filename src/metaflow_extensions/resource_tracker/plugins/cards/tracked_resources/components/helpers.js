function prettyTimestamp(unixTimestamp) {
    const date = new Date(unixTimestamp);
    const options = { 
        year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZoneName: 'short'
    };
    // YYYY-MM-DD HH:MM:SS GMT+1
    return date.toLocaleString('sv-SE', options);
};

// source: https://dygraphs.com/tests/legend-formatter.html
function legendFormatter(data) {
    if (data.x == null) {
        return '<br>' + data.series.map(function(series) { return series.dashHTML + ' ' + series.labelHTML }).join('<br>');
    }
    var html = data.xHTML;
    data.series.forEach(function(series) {
        if (!series.isVisible) return;
        var labeledData = series.labelHTML + ': ' + series.yHTML;
        if (series.isHighlighted) {
            labeledData = '<b>' + labeledData + '</b>';
        }
        html += '<br>' + series.dashHTML + ' ' + labeledData;
    });
    return html;
};

function createGraph(divId, csvData, labelsDivId) {
    return new Dygraph(
        document.getElementById(divId),
        csvData,
        {
            labelsDiv: labelsDivId,
            // labelsKMB: true,
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
            ]
        }
    );
};