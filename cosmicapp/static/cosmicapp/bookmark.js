var bookmarkInfo = {};

/*
 * Determines the symbol to display for the bookmark based off whether or not
 * the item is bookmarked, and updates the HTML code in the bookmark's div accordingly.
 */
function setBookmarkSymbol(divID)
{
    if(bookmarkInfo[divID].count > 0)
        symbol = '<font color=gold>★</font>';
    else
        symbol = '☆';

    $('#' + divID).html(symbol);
};

/*
 * A handler function to handle click events on a bookmark symbol.  The handler builds and executes an ajax request that
 * creates or removes a given bookmark based on the current status of that individual bookmark.
 */
function bookmarkClickHandler()
{
    // Get the id of the container div for the bookmark, this id will also tell us what object the bookmark is for.
    divID = $(this).get(0).id;

    // Disable the click handler to prevent extra requests until the first request is complete and change to a loading symbol.
    $('#' + divID).off();
    $('#' + divID).html("◌");

    // Parse the divID to get the type and id of the object this bookmark is for.
    targetType = divID.split('_')[0];
    targetID = divID.split('_')[1];
    folderName = '';

    if(bookmarkInfo[divID].count > 0)
        action = 'remove';
    else
        action = 'add';

    // Send the request to add or remove the bookamrk to the server and update the div when the result comes back.
    $.ajax({
        type: "POST",
        url: "/bookmark/",
        data: { action: action, targetType: targetType, targetID: targetID, folderName: folderName },
        dataType: 'json',
        pageElement: $(this),
        success: function(response, textStatus, jqXHR)
            {
                divID = this.pageElement.get(0).id;

                if(response.code == 'added' || response.code == 'removed')
                {
                    bookmarkInfo[divID] = response.info;
                    setBookmarkSymbol(divID);
                }
            },
        error: function(response, textStatus, jqXHR)
            {
                alert(response.responseJSON.error);
            },
        complete: function(response, textStatus, jqXHR)
            {
                // Restore the click handler to re-enable future click events.
                $('#' + divID).click(bookmarkClickHandler);
            }
    });
};

/*
 * Loops over all of the items on the page with a class of 'bookmark' and, using their id's, builds and executes an ajax
 * request to get the current bookmark status of each one.  After executing the ajax query, the div is filled in with an
 * appropriate symbol, indicating whether or not the item is bookmarked.  Finally, a click handler is assigned to
 * each one to handle future click events for each individual bookmark.
 */
$(document).ready(function()
{
    // Loop over all the bookmark divs on the page and form a space separated list of their id's to send to the server.
    // Also, change each bookmark div to the loading symbol, to indicate to the user that a request is in progress.
    divs = $('.bookmark').get();
    queryString = '';
    for(var i = 0; i < divs.length; i++)
    {
        queryString += divs[i].id + ' ';
        divs[i].innerHTML = "◌";
    }

    if(queryString != '')
    {
        // Send a query to the server asking for the status of every bookamrk on this page.
        $.ajax({
            type: "POST",
            url: "/bookmark/",
            data: { action: 'query', queryString: queryString },
            dataType: 'json',
            success: function(response, textStatus, jqXHR)
                {
                    // Store the response in the global variable bookmarkInfo so that the setBookmarkSymbol function
                    // knows what symbol to set for each bookmark.
                    bookmarkInfo = response;

                    // Loop over all the bookmark divs whose id's are present in the response and set an appropriate
                    // symbol, as well as enable the click handler to handle future user click events on each one.
                    for(divID in response)
                    {
                        setBookmarkSymbol(divID);
                        $('#' + divID).click(bookmarkClickHandler);
                    }
                },
            error: function(response, textStatus, jqXHR)
                {
                    alert(response.responseJSON.error);
                }
        });
    }
});

