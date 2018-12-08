/* globals django */
( function () {
	var prev;
	function findParent( el, selector ) {
		while ( true ) {
			if ( el.matches( selector ) ) {
				return el;
			}
			el = el.parentNode;
		}
	}

	function addAck( target, set ) {
		var block = findParent( target, 'li' );
		prev = block.innerHTML;
		fetch( set.getAttribute( 'data-add-handler' ) )
			.then( function ( res ) { return res.json(); } )
			.then( function ( res ) {
				block.innerHTML = res.form;
			} );
	}

	function submitAck( target, set ) {
		var formData = new FormData( findParent( target, 'form' ) );
		fetch( set.getAttribute( 'data-add-handler' ), {
			method: 'POST',
			body: formData
		} )
			.then( function ( res ) { return res.json(); } )
			.then( function ( res ) {
				var item = findParent( target, '.add-block' ),
					next;
				if ( res.form ) {
					item.innerHTML = res.form;
				}
				if ( res.success ) {
					next = item.cloneNode( true );
					next.innerHTML = prev;
					item.classList.remove( 'add-block' );
					item.classList.add( 'newly-added' );
					item.setAttribute( 'data-id', res.id );
					item.insertAdjacentHTML( 'afterend', next.outerHTML );
				}
			} );
	}

	function removeAck( target, set ) {
		var ackLine = findParent( target, 'li' ),
			block = findParent( target, '.remove-block' ),
			formData = new FormData();
		if ( block.classList.contains( 'really' ) ) {
			ackLine.classList.add( 'removing' );
			formData.append( 'id', ackLine.getAttribute( 'data-id' ) );
			formData.append( 'csrfmiddlewaretoken', set.getAttribute( 'data-token' ) );

			fetch( set.getAttribute( 'data-remove-handler' ), {
				method: 'POST',
				body: formData
			} )
				.then( function ( res ) { return res.json(); } )
				.then( function ( res ) {
					if ( res.success ) {
						ackLine.parentNode.removeChild( ackLine );
					} else {
						ackLine.classList.add( 'failed' );
					}
				} );
		} else {
			block.classList.add( 'really' );
		}
	}

	document.addEventListener( 'DOMContentLoaded', function () {
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
}( django.jQuery ) );
