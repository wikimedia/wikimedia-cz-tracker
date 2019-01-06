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
	deletionSubmit.addEventListener( 'click', () => {
		const inputs = document.querySelectorAll( '.existing-search-results input[type="checkbox"]' );

		const urls = [ ...inputs ]
			.filter( input => input.checked )
			.map( ( input ) => {
				return input.getAttribute( 'data-media-api-url' );
			} );

		for ( const url of urls ) {
			fetch( url, {
				method: 'DELETE',
				headers: {
					Accept: 'application/json',
					'Content-Type': 'application/json',
					'X-CSRFToken': cookies.getItem( 'csrftoken' )
				}
			} );
		}
	} );

	const imageContainer = document.querySelector( '.search-results' );

	const limitElement = document.querySelector( '#limit' );
	const categoryElement = document.querySelector( '#category' );
	const loadMoreButton = document.querySelector( '#load-more' );

	const byNameSubmit = document.querySelector( '#by-name-submit' );
	const byUserSubmit = document.querySelector( '#by-user-submit' );

	const existingImages = await ( await fetch( `/api/tracker/mediainfo/?ticket=${ticketNumber}` ) ).json();
	let existingImageNames = [];
	for ( const image of existingImages ) {
		existingImageNames.push( image.canonicaltitle );
	}

	let previousFetchMethod;

	byNameSubmit.addEventListener( 'click', async () => {
		const name = document.querySelector( '#by-name-input' ).value;
		await fetchAndFillImages( name, findByName );
		previousFetchMethod = 'name';
	} );

	byUserSubmit.addEventListener( 'click', async () => {
		const user = document.querySelector( '#by-user-input' ).value;
		await fetchAndFillImages( user, findByUser );
		previousFetchMethod = 'user';
	} );

	byUserSubmit.click(); // Load default set of images
	fetchAndFillExistingImages();

	loadMoreButton.addEventListener( 'click', async () => {
		const input = document.querySelector( `#by-${ previousFetchMethod }-input` ).value;

		let findFunction;

		if ( previousFetchMethod === 'name' ) {
			findFunction = findByName;
		} else if ( previousFetchMethod === 'user' ) {
			findFunction = findByUser;
		}

		await fetchAndFillImages(
			input,
			findFunction,
			loadMoreButton.getAttribute( 'data-continue' )
		);
	} );

	async function fetchAndFillImages( input, findFunction, continueFrom ) {
		const limit = parseInt( limitElement.value ) || undefined;
		const category = categoryElement.value;

		const response = await findFunction( input, limit, continueFrom );

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

		const imageElems = document.querySelectorAll( '.search-result img' );

		for ( const [ i, image ] of Object.entries( imageElems ) ) {
			image.addEventListener( 'click', () => {
				const checkbox = document.querySelectorAll( '.search-results input' )[ i ];

				checkbox.checked = !( checkbox.checked );
			} );
		}
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

		const imageElems = document.querySelectorAll( '.search-result img' );

		for ( const [ i, image ] of Object.entries( imageElems ) ) {
			image.addEventListener( 'click', () => {
				const checkbox = document.querySelectorAll( '.existing-search-results input' )[ i ];

				checkbox.checked = !( checkbox.checked );
			} );
		}
	}

	async function findByUser( user = mwUsername, limit = 25, continueFrom ) {
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

		return await getImages( options );
	}

	async function findByName( name, limit = 25, continueFrom ) {
		const options = {
			aisort: 'name',
			aidir: 'ascending',
			aiprefix: name,
			ailimit: limit
		};

		if ( continueFrom !== undefined ) {
			options.aicontinue = continueFrom;
		}

		return await getImages( options );
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

	async function getImages( requestParams = {} ) {
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
		const resBody = await ( await fetch( requestUrl ) ).json();

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
