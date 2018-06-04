function searchForObject()
{
    var objectName = document.getElementsByName('object')[0].value;

    $('#searchResultsDiv').html('Searching...');
    $('#searchResultsDiv').show();

    $.ajax({
        url : "/query/?queryfor=objectsNamed&limit=100&name=" + objectName,
        type : "get",
        async: true,
        dataType: 'json',
        success : function(response)
        {
            if(response.length > 0)
            {
                var html = '';
                for(i = 0; i < response.length; i++)
                {
                    html += response[i].type + ': <a href="' + response[i].url + '">' + response[i].identifier + '</a>&emsp;'
                    html += '<a href="/upload/?object=' + response[i].identifier + '&objectRA=' + response[i].ra + '&objectDec=' + response[i].dec + '">(Select)</a>';
                    html += '<br>';
                }
                $('#searchResultsDiv').html(html);
                $('#searchResultsDiv').show();
            }
            else
            {
                alert('No Results Found.');
                $('#searchResultsDiv').html('');
                $('#searchResultsDiv').hide();
            }
        },
        error : function(response)
        {
            var response = response.responseJSON;
            alert(response.errorMessage);
        }
    });
};

