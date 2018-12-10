{
	let previous;
	function findParent( el, selector ) {
		while ( true ) {
			if ( el.matches( selector ) ) {
				return el;
			}
			el = el.parentNode;
		}
	}

	function addAck( target, set ) {
		const block = findParent( target, 'li' );
		previous = block.innerHTML;
		fetch( set.getAttribute( 'data-add-handler' ) )
			.then( res => res.json() )
			.then( ( res ) => { block.innerHTML = res.form; } );
	}

	function submitAck( target, set ) {
		const formData = new FormData( findParent( target, 'form' ) );
		fetch( set.getAttribute( 'data-add-handler' ), {
			method: 'POST',
			body: formData
		} )
			.then( response => response.json() )
			.then( ( response ) => {
				const item = findParent( target, '.add-block' );
				if ( response.form ) {
					item.innerHTML = response.form;
				}
				if ( response.success ) {
					const next = item.cloneNode( true );
					next.innerHTML = previous;
					item.classList.remove( 'add-block' );
					item.classList.add( 'newly-added' );
					item.setAttribute( 'data-id', response.id );
					item.insertAdjacentHTML( 'afterend', next.outerHTML );
				}
			} );
	}

	function removeAck( target, set ) {
		const ackLine = findParent( target, 'li' ),
			block = findParent( target, '.remove-block' ),
			formData = new FormData();
		if ( block.classList.contains( 'really' ) ) {
			ackLine.classList.add( 'removing' );
			formData.append( 'id', ackLine.getAttribute( 'data-id' ) );
			formData.append( 'csrfmiddlewaretoken', set.getAttribute( 'data-token' ) );

			fetch( set.getAttribute( 'data-remove-handler' ), {
				method: 'POST',
				body: formData
			} ).then( response => response.json() )
				.then( ( reponse ) => {
					if ( reponse.success ) {
						ackLine.parentNode.removeChild( ackLine );
					} else {
						ackLine.classList.add( 'failed' );
					}
				} );
		} else {
			block.classList.add( 'really' );
		}
	}

	document.addEventListener( 'DOMContentLoaded', () => {
		document.querySelector( '.ack-set' ).addEventListener( 'click', function ( event ) {
			if ( event.target.classList.contains( 'add-ack' ) ) {
				addAck( event.target, this );
				return false;
			}
			if ( event.target.classList.contains( 'submit-ack' ) ) {
				submitAck( event.target, this );
				return false;
			}
			if ( event.target.classList.contains( 'remove-ack' ) ) {
				removeAck( event.target, this );
				return false;
			}
		} );
	} );
}
