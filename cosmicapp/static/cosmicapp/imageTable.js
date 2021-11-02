//TODO: Add a parameter with an array of links to include in the hide/zoom div.
function ImageGallery(galleryName, paramString, displayType, includeLinks, imageOnclickFunction, thumbnailSize)
{
    this.name = galleryName;
    this.initParamString = paramString;
    if(displayType != '')
        this.displayType = displayType;
    else
        this.displayType = 'gallery';

    this.includeLinks = includeLinks;
    this.imageOnclickFunction = imageOnclickFunction;
    this.thumbnailSize = thumbnailSize;

    this.numRows = 2;
    this.numCols = 4;

    this.firstLoadOfGallery = true;
    this.loadingInProgress = false;

    this.paramIdCounter = 0;

    this.lastParamString = '';
    this.offset = 0;

    this.images = [];

    this.getImageById = function(id)
    {
        var i;
        for(i = 0; i < this.images.length; i++)
        {
            if(this.images[i].id == id)
                return this.images[i];
        }

        return null;
    };

    this.initImageGallery = function()
    {
        $(window).on('resize', this.handleWindowResize)
        this.handleWindowResize();

        this.addQueryParameter(this.initParamString);
        this.loadImageGalleryResults();
    };

    this.addQueryParameter = function(paramString)
    {
        var i;
        var html;
        var kv, key, value;

        if(paramString === undefined || paramString == '')
            paramString = 'imageProperty=';

        //TODO: This is just undoing the doubleEscape of the : symbol and splitting on :, see if there is a library function to do this.
        var params = [];
        var startIndex = 0;
        for(i = 0; i < paramString.length-1; i++)
        {
            if(paramString[i] == ':' && paramString[i+1] != ':' && paramString[i-1] != ':')
            {
                params[params.length] = paramString.substring(startIndex, i);
                startIndex = i+1;
            }

            if(paramString[i] == ':' && paramString[i-1] == ':')
            {
                paramString = paramString.replace('::', ':');
                i--;
            }
        }
        params[params.length] = paramString.substring(startIndex, paramString.length);

        for(i = 0; i < params.length; i++)
        {
            html = ''

            this.paramIdCounter++;

            html += '<div id="paramDiv_' + this.paramIdCounter + '" class="imageGalleryParameter ' + this.name + '">';
            if(this.paramIdCounter > 1)
                html += '<i>AND</i>&nbsp;';

            html += '<select class="paramSelect ' + this.name + '" id="paramSelect_' + this.name + '_' + this.paramIdCounter + '">'
            html += '<option value="user">User</option>'
            html += '<option value="id">Image ID</option>'
            html += '<option value="imageProperty">Image Property</option>'
            html += '<option value="questionAnswer">Question Answer</option>'
            html += '<option value="uploadSessionId">Upload Session ID</option>'
            html += '</select>&nbsp;'

            kv = params[i].split('=');
            key = kv[0];
            //NOTE: The slice and join here handles when the value portion contains an '=' sign in the original input.
            value = kv.slice(1, kv.length).join('=');

            html += '<input class="paramTextbox ' + this.name + '" type=text id="paramTextbox_' + this.name + '_' + this.paramIdCounter + '" value="' + value + '">';

            if(this.paramIdCounter > 1)
                html += '&nbsp;<input type=button class="button ' + this.name + '" style="margin: 3px" value="Remove" id="removeButton' + this.paramIdCounter + '"><br>'

            html += '</div>'

            $('#imageGalleryQueriesDiv.' + this.name).append(html);

            $('#paramSelect_' + this.name + '_' + this.paramIdCounter + '.' + this.name).val(key);
            $('#removeButton' + this.paramIdCounter + '.' + this.name).click(function()
            {
                $(this).parent().remove();
            });
        }
    };

    this.queryHelp = function()
    {
        var html = '';

        html += '<div class="imageGalleryZoomWindow ' + this.name + '">';
        html += '<div style="padding: 2em; background: white; width: 70%; overflow-y: auto;">'
        html += '<h2>Query Help</h2>'
        html += `
                <p>The image gallery is used on many pages and allows you to select and view a list of images which are
                pulled from the server using a database query.  Changing the query parameters allows you to limit the
                displayed images to a specific subset of the images in the database.</p>

                <h3>Default Query Filter</h3>
                <p>On most pages, when the gallery loads the default query will be to show your own images, starting from
                your most recently uploaded images and going back from there.  On these pages you will see a single filter
                listed, showing 'User' as the filter type and your username in the text box beside it.  Changing the
                username in the field will show images created by that user for future loading operations, but will not
                clear the already loaded images unless you press the 'Clear Results' button first.</p>

                <h3>Additional Filters</h3>
                <p>Clicking the 'Add Query Filter' button will add a second filter to further limit the returned results.
                You can choose from several types of filters using the dropdown box on the left and then enter the text for
                the filter into the text box on the right.</p>

                <h3>Logical Operators: <i>AND</i> and <i>OR</i></h3>
                <p>If multiple filters are selected the returned results must meet <i>all</i> of the conditions specified
                in the filters.  In technical terms this means the filters are combined using the logical <i>AND</i>
                operator.  You can also specify that you want to return all images that meet any one of several different
                conditions by separating the conditions using a pipe character (which looks like | and is found near the
                'Enter' key on most keyboards).  The pipe character represents the logical <i>OR</i> operator.</p>

                <p>Note that when using the | character, any spaces before or after the character will be stripped away so
                'user1|user2' is equivalent to 'user1 | user2'.  Use whichever is more convenient for you.</p>

                <h3>Examples</h3>
                <p>Show all your calibration frames:</p>
                <table border=2px>
                    <tr><th> Filter </th><th> Value </th></tr>
                    <tr><td> User </td><td> yourUserName </td></tr>
                    <tr><td> <i>AND</i> Image Property </td><td> imageType=dark | imageType=bias | imageType=light </td></tr>
                </table>
                 `
        html += '</div>'
        html += '</div>';

        $(document.body).append(html);

        $('.imageGalleryZoomWindow.' + this.name).click(function()
        {
            $(this).remove();
        });
    };

    this.zoomImage = function(id)
    {
        var html = '';

        var image = this.getImageById(id);

        html += '<div class="imageGalleryZoomWindow ' + this.name + '">';
        html += '<img src="' + image.thumbUrlLarge + '">';
        html += '</div>';

        $(document.body).append(html);

        $('.imageGalleryZoomWindow.' + this.name).click(function()
        {
            $(this).remove();
        });
    };

    this.getParamArray = function()
    {
        var params = document.getElementsByClassName('imageGalleryParameter ' + this.name);
        var paramArray = [];
        for(i = 0; i < params.length; i++)
        {
            var paramId = params[i].getAttribute('id').split('_')[1];
            var key = document.getElementById('paramSelect_' + this.name + '_' + paramId).value;
            var value = document.getElementById('paramTextbox_' + this.name + '_' + paramId).value;
            paramArray[paramArray.length] = key + "=" + value
        }

        return paramArray;
    };

    this.loadImageGalleryResults = function()
    {
        if(!this.loadingInProgress)
        {
            this.loadingInProgress = true;

            var gallery = document.getElementById("imageGalleryDiv");
            var currentHTML = gallery.innerHTML;
            $('#imageGalleryDiv.' + this.name).append('<div id="imageGalleryLoadingMessage" class="' + this.name + '"><p>Loading...</p><div>');

            var paramArray = this.getParamArray();
            var paramString = paramArray.join('&');
            if(paramString != this.lastParamString)
                this.offset = 0;

            this.lastParamString = paramString;

            $.ajax({
                url: '/query/?queryfor=image&' + paramString + '&order=time_desc&limit=' + this.numRows*this.numCols +
                        '&offset=' + this.offset,
                context: this,
                dataType: 'json',
                success: this.parseGalleryLoadResponse
                });
        }
    };

    this.parseGalleryLoadResponse = function(response, statusCode)
    {
        var i;
        var html = ""

        $('#newResultsDivider.' + this.name).remove();
        if(!this.firstLoadOfGallery)
        {
            html += '<div class="clearfix"></div>';
            html += '<div id=newResultsDivider class="responsive ' + this.name;
            html += '" style="text-align: center; width: 95%; border: 1px solid blue">';
            if(response.length > 0)
                html += 'New Results:</div>'
            else
                html += 'No more results to display.</div>'
        }

        for(i = 0; i < response.length; i++)
        {
            var res = response[i];

            this.images[this.images.length] = res;
            var imageId = res.id;

            if(this.displayType == 'gallery')
            {
                html += '<div class="responsive ' + this.name + '" id="gallery_' + this.name + '_image_' + imageId + '" style="height: 400px; padding: 4px;">'
                html += '<div class="gallery">'

                html += this.inlineImageHTML(imageId, res);

                html += '<div class="desc ' + this.name + '">'
                //TODO: Make these <a> links an image icon instead of the placeholder text link that is here now.
                html += '<a class="functionLink hideLink ' + this.name + '" id="hideButton' + imageId + '">Hide</a>&nbsp;&nbsp;';
                html += '<a class="functionLink zoomLink ' + this.name + '" onclick="gallery_' + this.name + '.zoomImage(' + imageId + ')">Zoom</a>';
                html += '</div>';
                html += '</div>';
                html += '</div>';
            }
            else if(this.displayType == 'table')
            {
                html += '<div class="responsive ' + this.name + '" id="gallery_' + this.name + '_image_' + imageId + '" style="padding: 4px;">'
                html += '<table class="responsive ' + this.name + '"cellpadding=3px border=1px style="border-collapse: collapse; height: 11em;">';
                html += '<tr>';
                html += '<td>';
                html += this.inlineImageHTML(imageId, res);
                //html += '<td> <a href="/image/' + res.id + '"><img src="' + res.thumbUrlSmall + '"><br>Image ' + res.id + '</a> </td>';
                html += '</td>';
                html += '<td><font size=-1> ' + res.dimX + 'x' + res.dimY + 'x' + res.dimZ + ' ' + res.bitDepth + 'bits/pix<br>';
                html += 'Frame Type: ' + res.frameType + '<br>' + res.dateTime + '<br>';
                html += res.numPlateSolutions + ' Plate Solutions </font></td>';
                html += '</tr>';
                html += '</table>';
                html += '</div>';
            }

            this.offset += 1;
        }

        $('#imageGalleryLoadingMessage.' + this.name).remove();
        $('#imageGalleryDiv.' + this.name).append(html);
        if(!this.firstLoadOfGallery)
            $('#newResultsDivider.' + this.name)[0].scrollIntoView({behaviour: 'smooth', block: 'start', inline: 'start'});

        //TODO: These are probably getting added multiple times.  Need to test this and fix if necessary, this method is kind of hacky anyway.
        $(".hideLink." + this.name).click(function()
        {
            $(this).parent().parent().parent().remove();
        });

        $(document).trigger('imageTableLoadEvent_' + this.name);

        this.loadingInProgress = false;
        this.firstLoadOfGallery = false;
    };

    this.clearImageGalleryResults = function()
    {
        this.offset = 0;
        this.lastParamString = '';
        $('.responsive.' + this.name).remove();
    };

    this.handleWindowResize = function()
    {
        var width = $(window).width();
        var height = $(window).height();

        //NOTE: These width values should match the ones in style.css  If that changes need to change these too.
        if(width > 1000) { this.numCols = 4; }
        else if(width > 700) { this.numCols = 3; }
        else if(width > 400) { this.numCols = 4; }
        else { this.numCols = 3; }

        if(height > 900) { this.numRows = 4; }
        else if(height > 700) { this.numRows = 3; }
        else if(height > 500) { this.numRows = 2; }
        else { this.numRows = 2; }

        if(this.displayType == 'table')
            this.numRows *= 2;
    };

    this.saveQuery = function()
    {
        $('#' + this.name + '_saveQueryLink').hide();
        $('#' + this.name + '_saveQueryDiv').show();
    };

    this.saveQuerySubmit = function()
    {
        var queryName = document.getElementsByName(this.name + '_queryName')[0].value;
        var queryHeaderText = document.getElementsByName(this.name + '_queryHeaderText')[0].value;
        var queryText = document.getElementsByName(this.name + '_queryText')[0].value;
        var queryParams = this.getParamArray().join(':');

        var name = this.name;

        $.ajax({
            url : "/save/query/",
            type : "post",
            async: true,
            dataType: 'json',
            data: {
                queryName: queryName,
                queryHeaderText: queryHeaderText,
                queryText: queryText,
                queryParams: queryParams
            },
            success : function(response)
            {
                $('#' + name + '_saveQueryDiv').hide();
                $('#' + name + '_saveQueryLink').html('<a href="' + response.url + '">View your saved query</a>');
                $('#' + name + '_saveQueryLink').show();
            },
            error : function(response)
            {
                alert(response.responseText);
            }
        });
    };

    this.saveQueryCancel = function()
    {
        $('#' + this.name + '_saveQueryLink').show();
        $('#' + this.name + '_saveQueryDiv').hide();
    };

    this.getImageById = function(id)
    {
        var i;
        for(i = 0; i < this.images.length; i++)
        {
            if(this.images[i].id == id)
                return this.images[i];
        }

        return undefined;
    };

    this.selectImage = function(id)
    {
        $('#gallery_' + this.name + '_image_' + id).css('background', '#4e4');
    };

    this.unselectImage = function(id)
    {
        $('#gallery_' + this.name + '_image_' + id).css('background', 'none');
    };

    this.inlineImageHTML = function(imageId, res)
    {
        var html = '';
        if(this.includeLinks)
        {
            html += '<a href="/image/' + imageId + '/">'
            html += '<img src="' + res['thumbUrl'+this.thumbnailSize] + '">';
            html += '</a>';
        }
        else
        {
            html += '<img onclick="' + this.imageOnclickFunction + '(' + imageId + ',\'' + this.name + '\')" src="' + res['thumbUrl'+this.thumbnailSize] + '">';
        }

        return html;
    };
};

