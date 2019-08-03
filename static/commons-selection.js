( async () => {
	const ticketNumber = document.querySelector( '#ticket-number' ).value;

	const userProfile = await ( await fetch( '/api/tracker/trackerprofile/me' ) ).json();
	const mwUsername = userProfile.mediawiki_username;

	const userInput = document.querySelector( '#by-user-input' );
	userInput.setAttribute( 'value', mwUsername || '' );

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
		const name = document.querySelector( '#by-name-input' ).value;
		const user = document.querySelector( '#by-user-input' ).value;
		await fetchAndFillImages( name, user );
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

	loadMoreButton.addEventListener( 'click', async () => {
		loadingText.classList.remove( 'hidden' );
		loadMoreButton.classList.add( 'hidden' );

		const name = document.querySelector( '#by-name-input' ).value;
		const user = document.querySelector( '#by-user-input' ).value;

		await fetchAndFillImages(
			name,
			user,
			findFunction,
			loadMoreButton.getAttribute( 'data-continue' )
		);
	} );

	async function fetchAndFillImages( name, user, continueFrom ) {
		const limit = parseInt( limitElement.value ) || undefined;
		const category = categoryElement.value;

		const response = await findFunction( name, user, limit, continueFrom );

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
			imageElem.innerHTML = generateImageHtml( image, 'new' );

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
			imageElem.innerHTML = generateImageHtml( image, 'existing' );

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

	async function findFunction( name = '', user = mwUsername, limit = 25, continueFrom ) {
		if ( user === '' ) {
			return [];
		}

		const options = {
			aisort: 'timestamp',
			aidir: 'descending',
			aiuser: user,
			ailimit: limit
		};

		if ( continueFrom !== undefined ) {
			options.aicontinue = continueFrom;
		}

		const filteredName = name.replace( 'File:', '' ).replace( ' ', '_' ); // T214014
		return await getImages( options, filteredName );
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

	async function getImages( requestParams = {}, name = '' ) {
		const properties = [
			'timestamp', 'url', 'canonicaltitle', 'extmetadata', 'dimensions'
		];

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
		if ( name !== '' ) {
			// Filter names locally, can't use aiprefix, because that requires ordering by name
			// and not by timestamp.
			let toRemove = [];
			for ( let i = 0; i < resBody.query.allimages.length; i++ ) {
				const element = resBody.query.allimages[ i ];
				if ( !element.name.startsWith( name ) ) {
					toRemove.push( i );
				}
			}
			for ( let i = 0; i < toRemove.length; i++ ) {
				const index = toRemove[ i ];
				resBody.query.allimages.splice( index );
			}
		}

		return {
			images: resBody.query.allimages,
			'continue':
				resBody.continue ?
					resBody.continue.aicontinue :
					undefined
		};
	}

	function generateImageHtml( image, idExtra ) {
		let thumbUrl;
		if ( image.thumb_url !== undefined ) {
			thumbUrl = image.thumb_url;
		} else {
			thumbUrl = fileToThumb( image );
		}

		let extraCheckboxAttr = '';
		if ( image.apiUrl ) {
			extraCheckboxAttr = `data-media-api-url="${ image.apiUrl }"`;
		}

		return `
			<img src="${ thumbUrl }" alt="" height=${ Math.max( image.height, 200 ) }>

			<input type="checkbox" name="${ image.canonicaltitle }" id="${ idExtra }-${ image.canonicaltitle }" ${ extraCheckboxAttr }>
			<label for="${ idExtra }-${ image.canonicaltitle }">Select</label>

			<p>
				<a href="${ image.descriptionurl }">
					${ image.canonicaltitle.substring( 5, ) }
				</a>
			</p>
		`;
	}

	function fileToThumb( image ) {
		const url = image.url;
		const urlRegex = /^https:\/\/upload\.wikimedia\.org\/wikipedia\/commons\/([0-9a-f])\/([0-9a-f]{2})\/(.+?\.(.+))$/gmi;

		if ( !urlRegex.test( url ) ) {
			throw new Error( 'Image URL is not in the expected format. This is probably an internal error.' );
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
