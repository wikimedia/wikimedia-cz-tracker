( async () => {
	const ticketNumber = document.querySelector( '#ticket-number' ).value;

	const userProfile = await ( await fetch( '/api/tracker/trackerprofile/me' ) ).json();
	const mwUsername = userProfile.mediawiki_username;

	const findByDataEl = document.querySelector( 'input[name="find-by-data"]' );
	findByDataEl.setAttribute( 'value', mwUsername || '' );

	const selectionSubmit = document.querySelector( '#selection-submit' );

	selectionSubmit.addEventListener( 'click', async () => {
		const inputs = document.querySelectorAll( '.search-results input[type="checkbox"]' );

		const requestData = [ ...inputs ]
			.filter( input => input.checked )
			.map( ( input ) => {
				return {
					name: input.name,
					ticket: `/api/tracker/tickets/${ ticketNumber }/`
				};
			} );

		try {
			let resp = await fetch( '/api/tracker/mediainfo/', {
				method: 'POST',
				headers: {
					Accept: 'application/json',
					'Content-Type': 'application/json',
					'X-CSRFToken': cookies.getItem( 'csrftoken' )
				},
				body: JSON.stringify( requestData ),
				credentials: 'same-origin'
			} );

			if ( resp.status >= 400 ) {
				window.location.href += 'error/';
			}
			window.location.href += 'success/';
		} catch ( err ) {
			window.location.href += 'error/';
		}
	} );

	const deletionSubmit = document.querySelector( '#deletion-submit' );
	deletionSubmit.addEventListener( 'click', async () => {
		const inputs = document.querySelectorAll( '.existing-search-results input[type="checkbox"]' );

		const urls = [ ...inputs ]
			.filter( input => input.checked )
			.map( ( input ) => {
				return input.getAttribute( 'data-media-api-url' );
			} );

		try {
			for ( const url of urls ) {
				let resp = await fetch( url, {
					method: 'DELETE',
					headers: {
						Accept: 'application/json',
						'Content-Type': 'application/json',
						'X-CSRFToken': cookies.getItem( 'csrftoken' )
					}
				} );

				if ( resp.status >= 400 ) {
					window.location.href += 'error/';
				}
			}

			window.location.href += 'success/';
		} catch ( err ) {
			window.location.href += 'error/';
		}
	} );

	const imageContainer = document.querySelector( '.search-results' );

	const limitElement = document.querySelector( '#limit' );
	const categoryElement = document.querySelector( '#category' );
	const loadMoreButton = document.querySelector( '#load-more' );
	const loadingText = document.querySelector( '#loading' );

	const btnSearch = document.querySelector( '#btn-search' );
	const btnSelectAll = document.querySelector( '#btn-select-all' );
	const btnDeselectAll = document.querySelector( '#btn-deselect-all' );
	const btnInvertSelection = document.querySelector( '#btn-invert-all' );
	const radioFindBy = document.querySelectorAll( 'input[name="find-by"]' );

	const existingImages = await ( await fetch( `/api/tracker/mediainfo/?ticket=${ ticketNumber }` ) ).json();
	let existingImageNames = [];
	for ( const image of existingImages ) {
		if ( image.canonicaltitle !== null ) {
			existingImageNames.push( image.canonicaltitle );
		} else {
			existingImageNames.push( image.name );
		}
	}

	let previousCheck;

	btnSearch.addEventListener( 'click', async () => {
		imageContainer.innerHTML = '';
		loadingText.classList.remove( 'hidden' );
		loadMoreButton.classList.add( 'hidden' );
		await fetchAndFillImages();
	} );

	btnSearch.click(); // Load default set of images
	fetchAndFillExistingImages();

	let shiftPressed = false;

	window.addEventListener( 'keydown', ( e ) => {
		if ( e.key === 'Shift' ) {
			shiftPressed = true;
		}
	} );

	window.addEventListener( 'keyup', ( e ) => {
		if ( e.key === 'Shift' ) {
			shiftPressed = false;
		}
	} );

	btnSelectAll.addEventListener( 'click', () => {
		document.querySelectorAll( '.search-result > input' ).forEach( ( el ) => {
			el.checked = true;
		} );
	} );

	btnDeselectAll.addEventListener( 'click', () => {
		document.querySelectorAll( '.search-result > input' ).forEach( ( el ) => {
			el.checked = false;
		} );
	} );

	btnInvertSelection.addEventListener( 'click', () => {
		document.querySelectorAll( '.search-result > input' ).forEach( ( el ) => {
			el.checked = !el.checked;
		} );
	} );

	radioFindBy.forEach( ( el ) => {
		el.addEventListener( 'change', () => {
			const findByType = document.querySelector( 'input[name="find-by"]:checked' ).value;

			if ( findByType === 'user' ) {
				findByDataEl.setAttribute( 'value', mwUsername || '' );
			} else {
				findByDataEl.setAttribute( 'value', '' );
			}

			switch ( findByType ) {
				case 'user':
					document.querySelector( '#find-by-label' ).innerText = gettext( 'Mediawiki username' );
					break;
				case 'filename':
					document.querySelector( '#find-by-label' ).innerText = gettext( 'Filename prefix' );
					break;
			}
		} );
	} );

	loadMoreButton.addEventListener( 'click', async () => {
		loadingText.classList.remove( 'hidden' );
		loadMoreButton.classList.add( 'hidden' );

		await fetchAndFillImages(
			loadMoreButton.getAttribute( 'data-continue' )
		);
	} );

	async function fetchAndFillImages( continueFrom ) {
		try {
			await fetchAndFillImagesInternal(
				document.querySelector( 'input[name="find-by"]:checked' ).value,
				document.querySelector( 'input[name="find-by-data"]' ).value,
				continueFrom
			);
		} catch ( error ) {
			console.error( error ); // eslint-disable-line
			window.showMessage(
				gettext( 'Unknown error happened while fetching images you uploaded. Please contact the server admin.' ),
				'alert-danger'
			);
		}
	}

	async function fetchAndFillImagesInternal( findType, findData, continueFrom ) {
		const limit = parseInt( limitElement.value ) || undefined;
		const category = categoryElement.value;

		const loadExternalMetadata = Boolean( category );

		const response = await findFunction( findType, findData, limit, continueFrom, loadExternalMetadata );

		if ( response.continue !== undefined ) {
			loadMoreButton.classList.remove( 'hidden' );
			loadMoreButton.setAttribute( 'data-continue', response.continue );
		} else {
			loadMoreButton.classList.add( 'hidden' );
			loadMoreButton.removeAttribute( 'data-continue' );
		}

		const images = filterByCategory( response.images, category );

		if ( continueFrom === undefined ) {
			removeChildren( imageContainer );
		}

		for ( const image of images ) {
			if ( existingImageNames.includes( image.canonicaltitle ) ) {
				continue;
			}
			const imageElem = document.createElement( 'div' );
			imageElem.classList.add( 'search-result' );
			imageElem.innerHTML = await generateImageHtml( image, 'new' );

			imageContainer.appendChild( imageElem );
		}

		const imageElements = document.querySelectorAll( '.search-results img' );
		const [ ...checkboxes ] = document.querySelectorAll( '.search-results input[type=checkbox]' );

		handleImageClick( imageElements, checkboxes );
		handleShiftCheck( checkboxes );

		loadingText.classList.add( 'hidden' );
	}

	async function fetchAndFillExistingImages() {
		const existingImageContainer = document.querySelector( '.existing-search-results' );
		removeChildren( existingImageContainer );

		for ( const image of existingImages ) {
			image.apiUrl = image.url;
			const imageElem = document.createElement( 'div' );
			imageElem.classList.add( 'search-result' );
			imageElem.innerHTML = await generateImageHtml( image, 'existing' );

			existingImageContainer.appendChild( imageElem );
		}

		const imageElements = document.querySelectorAll( '.existing-search-results img' );
		const [ ...checkboxes ] = document.querySelectorAll( '.existing-search-results input[type=checkbox]' );

		handleImageClick( imageElements, checkboxes );
		handleShiftCheck( checkboxes );
	}

	function handleImageClick( imageElements, checkboxes ) {
		for ( const [ i, image ] of Object.entries( imageElements ) ) {
			image.addEventListener( 'click', () => {
				const checkbox = checkboxes[ i ];

				checkbox.checked = !( checkbox.checked );

				checkbox.dispatchEvent( new Event( 'change' ) );
			} );
		}
	}

	function handleShiftCheck( checkboxes ) {
		for ( let i = 0; i < checkboxes.length; i++ ) {
			const checkbox = checkboxes[ i ];

			const handler = ( ( latestCheck ) => {
				return () => {
					if ( shiftPressed ) {
						const direction = ( latestCheck > previousCheck ) ? +1 : -1;

						for (
							let current = previousCheck + 1;
							Math.abs( latestCheck - current ) > 0;
							current += direction
						) {
							checkboxes[ current ].checked = !checkboxes[ current ].checked;
						}
					}

					previousCheck = latestCheck;
				};
			} )( i );

			checkbox.addEventListener( 'change', handler );
		}
	}

	async function findFunction( findType, findData, limit = 25, continueFrom, loadExternalMetadata = true ) {
		const options = {
			ailimit: limit
		};

		if ( findType === 'user' ) {
			options.aisort = 'timestamp';
			options.aidir = 'descending';
			options.aiuser = findData;
		} else if ( findType === 'filename' ) {
			options.aisort = 'name';
			options.aifrom = findData;
		} else {
			// This shouldn't ever happen
			throw new Error( 'Unknown findType in findFunction' );
		}

		if ( continueFrom !== undefined ) {
			options.aicontinue = continueFrom;
		}

		return await getImages( options, findType, loadExternalMetadata );
	}

	function filterByCategory( images, category ) {
		if ( !category ) {
			return images;
		}

		return images.filter( ( image ) => {
			const categories = image
				.extmetadata
				.Categories.value
				.split( '|' );

			return categories.includes( category );
		} );
	}

	async function getImageByName( name ) {
		const requestParams = {
			action: 'query',
			format: 'json',
			prop: 'imageinfo',
			titles: name,
			iiprop: 'timestamp|user|url'
		};

		const requestUrl = `/api/mediawiki/${ toQueryString( requestParams ) }`;
		let resBody = await ( await fetch( requestUrl ) ).json();
		const pageid = Object.keys( resBody.query.pages )[ 0 ];
		const image = resBody.query.pages[ pageid ];
		return {
			name: image.title,
			url: image.imageinfo[ 0 ].url
		};
	}

	async function getImages( requestParams = {}, findType = undefined, loadExternalMetadata = true ) {
		let properties = [
			'timestamp', 'url', 'canonicaltitle', 'dimensions'
		];
		if ( loadExternalMetadata ) {
			properties.push( 'extmetadata' );
		}

		const defaultParams = {
			action: 'query',
			list: 'allimages',
			ailimit: 25,
			aiprop: properties.join( '|' ),
			format: 'json'
		};

		requestParams = Object.assign( defaultParams, requestParams );

		const requestUrl = `/api/mediawiki/${ toQueryString( requestParams ) }`;
		let resBody = await ( await fetch( requestUrl ) ).json();
		if ( resBody.query === undefined ) {
			if ( resBody.error !== undefined ) {
				// MediaWiki returned an error - display a potentionally more meaningful error message

				window.showMessage(
					`${ gettext( 'Wikimedia Commons returned the following error' ) }: ${ resBody.error.info }`,
					'alert-danger'
				);
				// Return no images found
				return {
					images: [],
					'continue': undefined
				};
			}
		}
		let images = resBody.query.allimages;

		if ( images.length === 0 ) {
			if ( findType === 'user' ) {
				window.showMessage(
					gettext( 'Specified account does not have any uploads at Wikimedia Commons. Upload some files first!' ),
					'alert-danger'
				);
			} else {
				window.showMessage(
					gettext( 'Your search does not match any files.' ),
					'alert-danger'
				);
			}
		}

		return {
			images: images,
			'continue':
				resBody.continue ?
					resBody.continue.aicontinue :
					undefined
		};
	}

	async function generateImageHtml( image, idExtra ) {
		let thumbUrl;
		if ( image.thumb_url ) {
			thumbUrl = image.thumb_url;
		} else {
			thumbUrl = await fileToThumb( image );
		}

		let extraCheckboxAttr = '';
		if ( image.apiUrl ) {
			extraCheckboxAttr = `data-media-api-url="${ image.apiUrl }"`;
		}

		let title = image.canonicaltitle;
		if ( title === undefined || title === null ) {
			title = image.name; // Fallback
		}

		return `
			<img src="${ thumbUrl }" loading="lazy" alt="" height=${ Math.max( image.height, 200 ) }>

			<input type="checkbox" name="${ image.canonicaltitle }" id="${ idExtra }-${ image.canonicaltitle }" ${ extraCheckboxAttr }>
			<label for="${ idExtra }-${ image.canonicaltitle }">Select</label>

			<p>
				<a href="${ image.descriptionurl }">
					${ title }
				</a>
			</p>
		`;
	}

	async function fileToThumb( image ) {
		let url = image.url;
		const urlRegex = /^https:\/\/upload\.wikimedia\.org\/wikipedia\/commons\/([0-9a-f])\/([0-9a-f]{2})\/(.+?\.(.+))$/gmi;

		if ( !urlRegex.test( url ) ) {
			const trackerUrlRegex = /^https:\/\/tracker\.wikimedia\.cz\/api/gmi;
			if ( trackerUrlRegex.test( url ) && image.name !== undefined ) {
				let data = await ( getImageByName( image.name ) );
				url = data.url;
				if ( !urlRegex.test( url ) ) {
					throw new Error( 'Image URL is not in the expected format. This is probably an internal error.' );
				}
			} else {
				throw new Error( 'Image URL is not in the expected format. This is probably an internal error.' );
			}
		}

		urlRegex.lastIndex = 0;

		const [
			,
			hashFirst, hashFirstTwo,
			fullFilename,
			extension
		] = urlRegex.exec( url );

		const thumbSizePx = Math.min( image.width, 200 );

		let thumbExtension = 'jpg';

		if ( [ 'png', 'svg' ].includes( extension ) ) {
			thumbExtension = 'png';
		}

		let pageNumberString = '';

		if ( extension === 'pdf' ) {
			pageNumberString = 'page1-';
		}

		return `https://upload.wikimedia.org/wikipedia/commons/thumb/${ hashFirst }/${ hashFirstTwo }/${ fullFilename }/${ pageNumberString }${ thumbSizePx }px-${ fullFilename }.${ thumbExtension }`;
	}

	function removeChildren( elem ) {
		while ( elem.firstChild ) {
			elem.removeChild( elem.firstChild );
		}
	}

	function toQueryString( obj ) {
		let queryString = '?';

		for ( let [ key, value ] of Object.entries( obj ) ) {
			key = encodeURIComponent( key );
			value = encodeURIComponent( value );

			queryString += `${ key }=${ value }`;
			queryString += '&';
		}

		queryString = queryString.substr( 0, queryString.length - 1 );

		return queryString;
	}
} )();
