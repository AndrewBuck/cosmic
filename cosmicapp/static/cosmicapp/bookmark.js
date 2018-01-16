var bookmarkInfo = {};

/*
 * Determines the symbol to display for the bookmark based off whether or not
 * the item is bookmarked, and updates the HTML code in the bookmark's div accordingly.
 */
function setBookmarkSymbol(divID)
{
    div = document.getElementById(divID);
    folderName = div.getAttribute("data-folderName");

    if(bookmarkInfo[divID].count > 0)
    {
        if(bookmarkIsInFolder(divID, folderName))
            symbol = '<font color=gold>★</font>';
        else
            symbol = '<font color=orange>✢</font>';
    }
    else
        symbol = '☆';

    $('#' + divID).html(symbol);
};

/*
 * Checks to see if the bookmark for the given divID is in the specified folder,
 * returning true if it is and false if it is not.
 */
function bookmarkIsInFolder(divID, folderName)
{
    var folderFound = false;
    for(var i = 0; i < bookmarkInfo[divID].folders.length; i++)
    {
        if(bookmarkInfo[divID].folders[i] == folderName)
        {
            folderFound = true;
            break;
        }
    }

    return folderFound;
};

/*
 * A handler function to handle click events on a bookmark symbol.  The handler builds and executes an ajax request that
 * creates or removes a given bookmark based on the current status of that individual bookmark.
 */
function bookmarkClickHandler()
{
    // Get the id of the container div for the bookmark.
    var divID = $(this).get(0).id;
    var div = $(this).get(0);

    // Disable the click handler to prevent extra requests until the first request is complete and change to a loading symbol.
    $('#' + divID).off();
    $('#' + divID).html("◌");

    // Get the type and id of the object this bookmark is for.
    targetType = div.getAttribute("data-targetType");
    targetID = div.getAttribute("data-targetID");
    folderName = div.getAttribute("data-folderName");

    if(bookmarkIsInFolder(divID, folderName))
        action = 'remove';
    else
        action = 'add';

    // Send the request to add or remove the bookamrk to the server and update the div when the result comes back.
    $.ajax({
        type: "POST",
        url: "/bookmark/",
        data: { action: action, targetType: targetType, targetID: targetID, folderName: folderName },
        dataType: 'json',
        success: function(response, textStatus, jqXHR)
            {
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

