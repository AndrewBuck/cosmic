function handleRADecClick(domObject)
{
    var i;
    var raDecimal = Number($(domObject).parent().attr('data-raDecimal'));
    var decDecimal = Number($(domObject).parent().attr('data-decDecimal'));
    var extraMapParams = $(domObject).parent().attr('data-extraMapParams');
    var innerSpan = $(domObject).parent().children('span');
    var wasHidden;
    var markerEnabled = true;

    if(extraMapParams === undefined)
        extraMapParams = "";
    else
        markerEnabled = false;

    // If the raDec is being clicked on for the first time (i.e. displaying the dropdown)
    if(!innerSpan.is(":visible"))
    {
        $('.raDecInner').html('');
        $('.raDecInner').hide();
        wasHidden = true;

        var otherCoords = document.getElementsByClassName('raDec');
        for(i = 0; i < otherCoords.length; i++)
        {
            var otherRaDecimal = $(otherCoords[i]).attr('data-raDecimal');
            var otherDecDecimal = $(otherCoords[i]).attr('data-decDecimal');

            //TODO: Replace this with a proper great circle distance calculation.
            var dRa = Math.abs(raDecimal - otherRaDecimal);
            var dDec = Math.abs(decDecimal - otherDecDecimal);
            var dist = Math.sqrt(dRa*dRa + dDec + dDec)
            if(dist < 20)
            {
                var greenValue = 255 - 5*dist;
                var redValue = 50 + 10*dist;
                otherCoords[i].style.background = 'rgb(' + redValue + ',' + greenValue + ',40)';
            }
            else
            {
                otherCoords[i].style.background = 'None';
            }

            $(otherCoords[i]).children('span').html('');
            $(otherCoords[i]).children('span').hide();
        }
    }
    else
    {
        wasHidden = false;
        $('.raDecInner').html('');
        $('.raDecInner').hide();
    }

    html = ''
    html += '<div>';
    html += raDecimal.toFixed(3) + '&deg;&emsp;'
    if(decDecimal > 0)
        html += '+';
    html += decDecimal.toFixed(3) + '&deg;';
    //TODO: Should set a zoom data- parameter like we do for raDecimal so it can be more contextually appropriate.
    html += '<br><a href="/map/sky/?zoom=12&lat=' + decDecimal + '&lon=' + raDecimal;
    if(markerEnabled)
        html += '&mlat=' + decDecimal + '&mlon=' + raDecimal;
    html += extraMapParams + '">View on Sky Map</a>';
    html += '</div>';
    if(wasHidden)
        innerSpan.show().html(html)
    else
        innerSpan.hide().html(html)
};

