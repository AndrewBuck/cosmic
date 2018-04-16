function createNewCommentForm(targetType, targetID)
{
    html = '';
    html += '<table style="background: #CCC; padding: 1em;">';
    html += '<tr>';
    html += '<td>';
    html += '<textarea id="comment_' + targetType + '_' + targetID + '_newCommentTextArea" rows=10 cols=50></textarea>';
    html += '<br>';
    html += '<input type=button value="Cancel" onclick="cancelNewCommentForm(\'' + targetType + '\',\'' + targetID + '\')">';
    html += '<input type=button value="Save Comment" onclick="saveNewComment(\'' + targetType + '\',\'' + targetID + '\')">';
    html += '</td>';
    html += '<td style="padding: 1em;">';
    html += 'You can use markdown<br>to style your comment.<br>Examples below:';
    html += '<br>';
    html += '<br><i>*italic*</i>';
    html += '<br><b>**bold**</b>';
    html += '<br>[A link to Example.com](http://example.com)<br>turns into <a href="http://example.com">A link to Example.com</a>';
    html += '</td>';
    html += '</tr>';
    html += '</table>';
    html += '';
    html += '';
    $('#' + targetType + '_' + targetID + '_newCommentFormDiv').hide();
    $('#' + targetType + '_' + targetID + '_newCommentFormDiv').html(html);
    $('#' + targetType + '_' + targetID + '_newCommentFormDiv').show();
    $('#' + targetType + '_' + targetID + '_newCommentFormButton').hide();
    $('#comment_' + targetType + '_' + targetID + '_newCommentTextArea')[0].scrollIntoView({behaviour: 'smooth', block: 'start', inline: 'start'});
    $('#comment_' + targetType + '_' + targetID + '_newCommentTextArea')[0].focus();
    blah = ''
};

function cancelNewCommentForm(targetType, targetID)
{
    $('#' + targetType + '_' + targetID + '_newCommentFormDiv').hide();
    $('#' + targetType + '_' + targetID + '_newCommentFormDiv').html('');
    $('#' + targetType + '_' + targetID + '_newCommentFormButton').show();
};

function saveNewComment(targetType, targetID)
{
    var commentText = $('#comment_' + targetType + '_' + targetID + '_newCommentTextArea').get(0).value;

    if(commentText == "")
    {
        alert("No comment entered.");
        return;
    }

    $.ajax({
        url : "/save/comment/",
        type : "post",
        async: true,
        dataType: 'json',
        data: {
            targetType: targetType,
            targetID: targetID,
            commentText: commentText
        },
        success : function(response)
        {
            //Force a page reload.
            //TODO: This seems hacky, see if there is a better way of doing this.
            window.location = " " + window.location;
        },
        error : function(response)
        {
            var response = response.responseJSON;
            alert(response.errorMessage);
        }
    });
};

function showHideComment(commentID)
{
    toggleHTML = $('#commentToggle_' + commentID).html()
    if(toggleHTML == '-')
    {
        $('#commentToggle_' + commentID).html('+')
        $('#comment_' + commentID).hide(500);
    }
    else
    {
        $('#commentToggle_' + commentID).html('-')
        $('#comment_' + commentID).show();
        $('#commentToggle_' + commentID)[0].scrollIntoView({behaviour: 'smooth', block: 'start', inline: 'start'});
    }
};

function moderateComment(modDropdown)
{
    var html = '';
    var modValue = $('#'+modDropdown.id).get(0).value;
    var commentID = modDropdown.id.split('_')[1];

    if(modValue == '')
        return;

    $.ajax({
        url : "/save/moderation/",
        type : "post",
        async: true,
        dataType: 'json',
        data: {
            commentID: commentID,
            modValue: modValue
        },
        success : function(response)
        {
            $('#'+modDropdown.id).hide(1000);

            html += response.message + '&emsp;<input type=button class=button value="Undo Moderation"';
            html += 'onclick="undoModeration(\'' + response.moderationID + '\',\'' + modDropdown.id + '\')">';
            $('#'+modDropdown.id+'Span').html(html);
        },
        error : function(response)
        {
            response = response.responseJSON;
            html += response.errorMessage + '&emsp;<input type=button class=button value="Undo Moderation"';
            html += 'onclick="undoModeration(\'' + response.moderationID + '\',\'' + modDropdown.id + '\')">';
            $('#'+modDropdown.id+'Span').html(html);
        }
    });

};

function undoModeration(moderationID, modDropdownID)
{
    $.ajax({
        url : "/delete/moderation/",
        type : "post",
        async: true,
        dataType: 'json',
        data: {
            moderationID: moderationID
        },
        success : function(response)
        {
            $('#'+modDropdownID).show(1000);
            $('#'+modDropdownID+'Span').html('');
        },
        error : function(response)
        {
            response = response.responseJSON;
            alert(response.errorMessage);
        }
    });

};

